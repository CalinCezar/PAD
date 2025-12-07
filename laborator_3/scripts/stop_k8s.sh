#!/bin/bash

echo "=========================================="
echo "  Removing Kubernetes Deployments"
echo "=========================================="

# Delete all resources
echo "Deleting all resources..."

kubectl delete -f kubernetes/datawarehouse-service.yaml
kubectl delete -f kubernetes/datawarehouse-deployment.yaml
kubectl delete -f kubernetes/xmlnode-service.yaml
kubectl delete -f kubernetes/xmlnode-deployment.yaml
kubectl delete -f kubernetes/jsonnode-service.yaml
kubectl delete -f kubernetes/jsonnode-deployment.yaml
kubectl delete -f kubernetes/mongodb-service.yaml
kubectl delete -f kubernetes/mongodb-deployment.yaml
kubectl delete -f kubernetes/mongodb-pvc.yaml

echo ""
echo "✓ All resources deleted"
echo ""
echo "Verify deletion:"
echo "  kubectl get all"
echo ""
