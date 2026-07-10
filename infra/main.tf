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
# Azure Container Registry
# ---------------------------------------------------------------------------

resource "azurerm_container_registry" "main" {
  name                = "cr${var.project_name}${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Container Apps (FastAPI backend)
# ---------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name_suffix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

resource "azurerm_container_app" "api" {
  name                         = "ca-${local.name_suffix}"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  template {
    container {
      name   = "fastapi"
      image  = "${azurerm_container_registry.main.login_server}/layakb-api:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "AZURE_STORAGE_CONNECTION_STRING"
        value = azurerm_storage_account.main.primary_connection_string
      }
      env {
        name  = "AZURE_STORAGE_CONTAINER_NAME"
        value = azurerm_storage_container.documents.name
      }
      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.main.name}.search.windows.net"
      }
      env {
        name  = "AZURE_SEARCH_API_KEY"
        value = azurerm_search_service.main.primary_key
      }
      env {
        name  = "AZURE_SEARCH_INDEX_NAME"
        value = "knowledge-base"
      }
      env {
        name  = "AZURE_COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.main.endpoint
      }
      env {
        name  = "AZURE_COSMOS_KEY"
        value = azurerm_cosmosdb_account.main.primary_key
      }
      env {
        name  = "AZURE_COSMOS_DATABASE"
        value = azurerm_cosmosdb_sql_database.main.name
      }
      env {
        name  = "AZURE_COSMOS_CONTAINER"
        value = azurerm_cosmosdb_sql_container.documents.name
      }
      env {
        name  = "ARK_API_KEY"
        value = var.ark_api_key
      }
      env {
        name  = "ARK_BASE_URL"
        value = var.ark_base_url
      }
      env {
        name  = "ARK_CHAT_MODEL"
        value = var.ark_chat_model
      }
      env {
        name  = "ARK_EMBEDDING_MODEL"
        value = var.ark_embedding_model
      }
      env {
        name  = "ARK_EMBEDDING_BASE_URL"
        value = var.ark_embedding_base_url
      }
      env {
        name  = "API_BASE_URL"
        value = "https://ca-${local.name_suffix}.${azurerm_container_app_environment.main.default_domain}"
      }
    }

    min_replicas = 0
    max_replicas = 1
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
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

# ---------------------------------------------------------------------------
# Azure Static Web Apps (React frontend)
# ---------------------------------------------------------------------------

resource "azurerm_static_web_app" "frontend" {
  name                = "swa-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = "eastus2"
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.tags
}
