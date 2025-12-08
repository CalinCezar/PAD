#!/bin/bash
# Azure Cleanup Script - Remove all resources
# Employee Data Warehouse - PAD Laboratory 3

set -e

RESOURCE_GROUP="EmployeeDataWarehouse-RG"

echo "=========================================="
echo "  Azure Cleanup - Employee Data Warehouse"
echo "=========================================="
echo ""

echo "WARNING: This will delete ALL resources in the resource group: $RESOURCE_GROUP"
read -p "Are you sure? (yes/no): " confirmation

if [ "$confirmation" != "yes" ]; then
    echo "Cleanup cancelled"
    exit 0
fi

echo ""
echo "Deleting resource group: $RESOURCE_GROUP"
echo ""

az group delete \
    --name $RESOURCE_GROUP \
    --yes \
    --no-wait

echo ""
echo "✓ Resource group deletion initiated"
echo "Note: Deletion may take several minutes to complete"
echo ""
echo "To check status:"
echo "  az group show --name $RESOURCE_GROUP"
echo ""
