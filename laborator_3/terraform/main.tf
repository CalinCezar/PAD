# Terraform configuration for Employee Data Warehouse on Azure
# Infrastructure as Code (IaC) for PAD Laboratory 3

terraform {
  required_version = ">= 1.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# Variables
variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
  default     = "EmployeeDataWarehouse-RG"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus"
}

variable "acr_name" {
  description = "Name of Azure Container Registry"
  type        = string
  default     = "employeedwregistry"
}

variable "aks_cluster_name" {
  description = "Name of AKS cluster"
  type        = string
  default     = "employee-dw-aks"
}

variable "cosmosdb_account_name" {
  description = "Name of Cosmos DB account"
  type        = string
  default     = "employee-dw-cosmosdb"
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    Project     = "Employee Data Warehouse"
    Environment = "Production"
    Lab         = "PAD-Lab3"
    ManagedBy   = "Terraform"
  }
}

# Azure Container Registry
resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true

  tags = {
    Project = "Employee Data Warehouse"
    Lab     = "PAD-Lab3"
  }
}

# Azure Kubernetes Service (AKS)
resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.aks_cluster_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "employee-dw"

  default_node_pool {
    name       = "default"
    node_count = 2
    vm_size    = "Standard_B2s"

    # Enable auto-scaling
    enable_auto_scaling = true
    min_count          = 1
    max_count          = 3
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin    = "azure"
    load_balancer_sku = "standard"
  }

  tags = {
    Project     = "Employee Data Warehouse"
    Environment = "Production"
    Lab         = "PAD-Lab3"
  }
}

# Role assignment for AKS to pull images from ACR
resource "azurerm_role_assignment" "aks_acr" {
  principal_id                     = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  role_definition_name             = "AcrPull"
  scope                            = azurerm_container_registry.acr.id
  skip_service_principal_aad_check = true
}

# Azure Cosmos DB for MongoDB API (replacing local MongoDB)
resource "azurerm_cosmosdb_account" "cosmosdb" {
  name                = var.cosmosdb_account_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "MongoDB"

  # Enable free tier (400 RU/s, 5GB storage)
  enable_free_tier = true

  capabilities {
    name = "EnableMongo"
  }

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

  tags = {
    Project = "Employee Data Warehouse"
    Lab     = "PAD-Lab3"
  }
}

# Cosmos DB MongoDB Database
resource "azurerm_cosmosdb_mongo_database" "mongodb" {
  name                = "employee_warehouse"
  resource_group_name = azurerm_cosmosdb_account.cosmosdb.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmosdb.name
}

# Cosmos DB MongoDB Collection
resource "azurerm_cosmosdb_mongo_collection" "employees" {
  name                = "employees"
  resource_group_name = azurerm_cosmosdb_account.cosmosdb.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmosdb.name
  database_name       = azurerm_cosmosdb_mongo_database.mongodb.name

  index {
    keys   = ["id"]
    unique = true
  }

  index {
    keys   = ["_id"]
    unique = true
  }
}

# Outputs
output "resource_group_name" {
  value       = azurerm_resource_group.main.name
  description = "Name of the resource group"
}

output "acr_login_server" {
  value       = azurerm_container_registry.acr.login_server
  description = "Login server for Azure Container Registry"
}

output "aks_cluster_name" {
  value       = azurerm_kubernetes_cluster.aks.name
  description = "Name of the AKS cluster"
}

output "aks_kube_config" {
  value     = azurerm_kubernetes_cluster.aks.kube_config_raw
  sensitive = true
  description = "Kubernetes configuration for AKS cluster"
}

output "cosmosdb_connection_string" {
  value     = azurerm_cosmosdb_account.cosmosdb.connection_strings[0]
  sensitive = true
  description = "Cosmos DB connection string"
}

output "cosmosdb_endpoint" {
  value       = azurerm_cosmosdb_account.cosmosdb.endpoint
  description = "Cosmos DB endpoint"
}
