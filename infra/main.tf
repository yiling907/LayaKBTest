locals {
  name_suffix = "${var.project_name}-${var.environment}"
  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Random suffix to ensure globally unique resource names
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_suffix}"
  location = var.location
  tags     = local.tags
}

# ---------------------------------------------------------------------------
# Storage Account  (Function App + document blobs)
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "main" {
  name                     = "st${var.project_name}${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = local.tags
}

resource "azurerm_storage_container" "documents" {
  name                  = "documents"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

# ---------------------------------------------------------------------------
# App Service Plan (Consumption / Serverless)
# ---------------------------------------------------------------------------

resource "azurerm_service_plan" "main" {
  name                = "asp-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1"  # Consumption plan
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Application Insights
# ---------------------------------------------------------------------------

resource "azurerm_application_insights" "main" {
  name                = "appi-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  application_type    = "web"
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Azure Function App  (Python 3.14)
# ---------------------------------------------------------------------------

resource "azurerm_linux_function_app" "main" {
  name                       = "func-${local.name_suffix}-${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.main.id
  storage_account_name       = azurerm_storage_account.main.name
  storage_account_access_key = azurerm_storage_account.main.primary_access_key

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.12"  # Use 3.12 until 3.14 is GA on Azure Functions
    }
    cors {
      allowed_origins = ["*"]
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME            = "python"
    APPINSIGHTS_INSTRUMENTATIONKEY      = azurerm_application_insights.main.instrumentation_key
    AZURE_STORAGE_CONNECTION_STRING     = azurerm_storage_account.main.primary_connection_string
    AZURE_STORAGE_CONTAINER_NAME        = azurerm_storage_container.documents.name
    AZURE_SEARCH_ENDPOINT               = "https://${azurerm_search_service.main.name}.search.windows.net"
    AZURE_SEARCH_API_KEY                = azurerm_search_service.main.primary_key
    AZURE_SEARCH_INDEX_NAME             = "knowledge-base"
    AZURE_OPENAI_ENDPOINT               = azurerm_cognitive_account.openai.endpoint
    AZURE_OPENAI_API_KEY                = azurerm_cognitive_account.openai.primary_access_key
    AZURE_OPENAI_API_VERSION            = "2024-02-01"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT   = "text-embedding-ada-002"
    AZURE_OPENAI_CHAT_DEPLOYMENT        = "gpt-4o"
    AZURE_COSMOS_ENDPOINT               = azurerm_cosmosdb_account.main.endpoint
    AZURE_COSMOS_KEY                    = azurerm_cosmosdb_account.main.primary_key
    AZURE_COSMOS_DATABASE               = azurerm_cosmosdb_sql_database.main.name
    AZURE_COSMOS_CONTAINER              = azurerm_cosmosdb_sql_container.documents.name
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Azure AI Search
# ---------------------------------------------------------------------------

resource "azurerm_search_service" "main" {
  name                = "srch-${local.name_suffix}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.search_sku
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

resource "azurerm_cognitive_account" "openai" {
  name                = "oai-${local.name_suffix}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  kind                = "OpenAI"
  sku_name            = var.openai_sku
  tags                = local.tags
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = "text-embedding-ada-002"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-ada-002"
    version = "2"
  }

  sku {
    name     = "Standard"
    capacity = 1
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-05-13"
  }

  sku {
    name     = "Standard"
    capacity = 1
  }
}

# ---------------------------------------------------------------------------
# Cosmos DB  (document metadata)
# ---------------------------------------------------------------------------

resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-${local.name_suffix}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = local.tags
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "layakbtest"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "documents" {
  name                = "documents"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/id"]
}
