# Remote state stored in Azure Blob Storage.
# Before running `terraform init`, create the storage account and container manually:
#
#   az group create -n rg-tfstate -l eastus
#   az storage account create -n <unique_name> -g rg-tfstate --sku Standard_LRS
#   az storage container create -n tfstate --account-name <unique_name>
#
# Then replace the placeholder values below.

terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate"
    storage_account_name = "tfstatelayakbtest"   # must be globally unique
    container_name       = "tfstate"
    key                  = "layakbtest.terraform.tfstate"
  }
}
