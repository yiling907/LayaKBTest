variable "project_name" {
  description = "Base name used for all resources"
  type        = string
  default     = "layakbtest"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod"
  }
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "search_sku" {
  description = "Azure AI Search SKU"
  type        = string
  default     = "free"
}

variable "ark_api_key" {
  description = "Ark API key"
  type        = string
  sensitive   = true
  default     = "c060ff83-9353-44f3-ac08-b3532370c9c7"
}

variable "ark_base_url" {
  description = "Ark API base URL (coding plan)"
  type        = string
  default     = "https://ark.cn-beijing.volces.com/api/coding/v3"
}

variable "ark_chat_model" {
  description = "Ark chat model ID"
  type        = string
  default     = "glm-5.2"
}

variable "ark_embedding_model" {
  description = "Ark embedding endpoint ID"
  type        = string
  default     = "ep-m-20260725051533-cjb9l"
}

variable "ark_embedding_base_url" {
  description = "Ark multimodal embedding endpoint URL"
  type        = string
  default     = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
}
