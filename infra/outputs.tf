output "api_url" {
  description = "FastAPI backend URL"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "acr_login_server" {
  description = "Azure Container Registry login server"
  value       = azurerm_container_registry.main.login_server
}

output "search_endpoint" {
  description = "Azure AI Search service endpoint"
  value       = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "storage_account_name" {
  description = "Storage account name"
  value       = azurerm_storage_account.main.name
}

output "cosmos_endpoint" {
  description = "Cosmos DB account endpoint"
  value       = azurerm_cosmosdb_account.main.endpoint
}

output "resource_group_name" {
  description = "Name of the main resource group"
  value       = azurerm_resource_group.main.name
}

output "frontend_url" {
  description = "Azure Static Web App URL"
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "swa_api_key" {
  description = "Azure Static Web App deployment API key"
  value       = azurerm_static_web_app.frontend.api_key
  sensitive   = true
}

output "mcp_url" {
  description = "MCP server URL"
  value       = "https://${azurerm_container_app.mcp.ingress[0].fqdn}/mcp"
}
