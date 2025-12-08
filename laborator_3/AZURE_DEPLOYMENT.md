# Azure Deployment Guide - Employee Data Warehouse

## PAD Laboratory 3 - Cloud Computing & CI/CD

Această documentație acoperă cerințele pentru Laboratorul 3:
- ✅ Utilizarea unui Cloud provider (Azure)
- ✅ Migrarea proiectului pe cloud
- ✅ Înlocuirea SGBD cu serviciu cloud (Azure Cosmos DB)
- ✅ Automatizarea provizionării infrastructurii (Terraform)
- ✅ Implementarea CI/CD (GitHub Actions)

---

## Cuprins

1. [Arhitectură Azure](#arhitectură-azure)
2. [Cerințe Preliminare](#cerințe-preliminare)
3. [Opțiuni de Deployment](#opțiuni-de-deployment)
4. [Deployment cu Terraform (IaC)](#deployment-cu-terraform-iac)
5. [Deployment Manual](#deployment-manual)
6. [CI/CD cu GitHub Actions](#cicd-cu-github-actions)
7. [Servicii Azure Utilizate](#servicii-azure-utilizate)
8. [Costuri și Optimizare](#costuri-și-optimizare)
9. [Monitorizare și Logs](#monitorizare-și-logs)
10. [Troubleshooting](#troubleshooting)

---

## Arhitectură Azure

```
┌─────────────────────────────────────────────────────────┐
│                   Internet / Users                       │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
                       ▼
┌─────────────────────────────────────────────────────────┐
│            Azure Load Balancer (Public IP)              │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│       Azure Kubernetes Service (AKS) Cluster            │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Data Warehouse Pods (3 replicas)                │  │
│  │  - Circuit Breaker                                │  │
│  │  - Rate Limiting                                  │  │
│  │  - Timeout handling                               │  │
│  │  Image: employeedwregistry.azurecr.io/dw:latest  │  │
│  └──────────────┬────────────────────┬───────────────┘  │
│                 │                    │                   │
│  ┌──────────────▼─────┐  ┌──────────▼─────────┐        │
│  │  JSON Node Pods    │  │  XML Node Pods     │        │
│  │  (2 replicas)      │  │  (2 replicas)      │        │
│  └────────────────────┘  └────────────────────┘        │
└─────────────────────────────────────────────────────────┘
                       │
                       │ MongoDB API
                       ▼
┌─────────────────────────────────────────────────────────┐
│        Azure Cosmos DB for MongoDB API                  │
│  - Database: employee_warehouse                          │
│  - Collection: employees                                 │
│  - Free Tier: 400 RU/s, 5GB storage                     │
│  - Global distribution                                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│        Azure Container Registry (ACR)                    │
│  - Docker images repository                              │
│  - Integrated with AKS                                   │
└─────────────────────────────────────────────────────────┘
```

---

## Cerințe Preliminare

### 1. Software Necesar

```bash
# Azure CLI
winget install -e --id Microsoft.AzureCLI
# Sau descarcă: https://aka.ms/installazurecliwindows

# kubectl (Kubernetes CLI)
az aks install-cli

# Terraform (pentru IaC)
winget install HashiCorp.Terraform

# Docker Desktop
# Descarcă: https://www.docker.com/products/docker-desktop
```

### 2. Cont Azure

- Cont Azure activ (Free tier disponibil)
- Subscription ID și Tenant ID
- Permisiuni pentru a crea resurse

**Obține Azure Free Account:**
- https://azure.microsoft.com/free/
- 200$ credit pentru 30 zile
- Multe servicii gratuite permanent

### 3. Verificare Instalare

```bash
# Verifică Azure CLI
az --version

# Verifică kubectl
kubectl version --client

# Verifică Terraform
terraform --version

# Verifică Docker
docker --version
```

---

## Opțiuni de Deployment

### Opțiunea 1: Terraform (RECOMANDAT) ⭐

**Avantaje:**
- Infrastructure as Code (IaC)
- Automatizare completă
- Reproducibil
- Version control pentru infrastructură

**Timp:** 15-20 minute

### Opțiunea 2: Script PowerShell/Bash

**Avantaje:**
- Mai simplu pentru începători
- Pas cu pas cu feedback
- Ușor de înțeles

**Timp:** 20-30 minute

### Opțiunea 3: GitHub Actions CI/CD

**Avantaje:**
- Deployment automat la fiecare commit
- Testare automată
- Professional workflow

**Timp:** 30-40 minute (setup inițial)

---

## Deployment cu Terraform (IaC)

### Pas 1: Configurare Terraform

```bash
# Navighează în directorul terraform
cd terraform

# Copiază fișierul de variabile
cp terraform.tfvars.example terraform.tfvars
```

**Editează `terraform.tfvars`:**
```hcl
subscription_id = "your-azure-subscription-id"
tenant_id       = "your-azure-tenant-id"
```

**Găsește Subscription ID și Tenant ID:**
```bash
az login
az account show --query "{subscriptionId:id, tenantId:tenantId}"
```

### Pas 2: Inițializează Terraform

```bash
# Inițializează Terraform (descarcă providers)
terraform init

# Verifică configurația
terraform validate

# Formatează fișierele
terraform fmt
```

### Pas 3: Preview Schimbări

```bash
# Vezi ce resurse vor fi create
terraform plan

# Output-ul va arăta:
# - 1 Resource Group
# - 1 Azure Container Registry
# - 1 AKS Cluster
# - 1 Cosmos DB Account
# - 1 Cosmos DB Database
# - 1 Cosmos DB Collection
```

### Pas 4: Aplică Infrastructura

```bash
# Creează toate resursele Azure
terraform apply

# Confirmă cu: yes
```

**Timpul de așteptare:**
- Resource Group: ~10 secunde
- ACR: ~2 minute
- Cosmos DB: ~5 minute
- AKS Cluster: ~10-15 minute

**Total: ~20 minute**

### Pas 5: Obține Output-uri

```bash
# Vezi toate output-urile
terraform output

# Obține connection string Cosmos DB (secret)
terraform output -raw cosmosdb_connection_string

# Obține ACR login server
terraform output -raw acr_login_server
```

### Pas 6: Build și Push Imagini

```bash
# Revino în directorul proiectului
cd ..

# Login la ACR
az acr login --name employeedwregistry

# Build imagini
docker build -f data_warehouse/Dockerfile -t employeedwregistry.azurecr.io/data-warehouse:latest .
docker build -f json_node/Dockerfile -t employeedwregistry.azurecr.io/json-node:latest .
docker build -f xml_node/Dockerfile -t employeedwregistry.azurecr.io/xml-node:latest .

# Push imagini
docker push employeedwregistry.azurecr.io/data-warehouse:latest
docker push employeedwregistry.azurecr.io/json-node:latest
docker push employeedwregistry.azurecr.io/xml-node:latest
```

### Pas 7: Deploy pe AKS

```bash
# Obține credentials AKS
az aks get-credentials \
  --resource-group EmployeeDataWarehouse-RG \
  --name employee-dw-aks \
  --overwrite-existing

# Creează namespace
kubectl create namespace employee-dw

# Creează secret pentru Cosmos DB
COSMOS_CONN=$(terraform output -raw cosmosdb_connection_string)
kubectl create secret generic cosmosdb-connection \
  --from-literal=connection-string="$COSMOS_CONN" \
  -n employee-dw

# Deploy aplicația
kubectl apply -f kubernetes/datawarehouse-deployment-azure.yaml -n employee-dw
kubectl apply -f kubernetes/jsonnode-deployment.yaml -n employee-dw
kubectl apply -f kubernetes/xmlnode-deployment.yaml -n employee-dw
kubectl apply -f kubernetes/datawarehouse-service.yaml -n employee-dw
kubectl apply -f kubernetes/jsonnode-service.yaml -n employee-dw
kubectl apply -f kubernetes/xmlnode-service.yaml -n employee-dw

# Verifică status
kubectl get pods -n employee-dw
kubectl get services -n employee-dw
```

### Pas 8: Testează Deployment

```bash
# Obține external IP
kubectl get service data-warehouse -n employee-dw

# Așteaptă până IP-ul devine disponibil
# Poate dura 2-3 minute

# Test health check
curl http://<EXTERNAL-IP>:5000/health

# Test API
curl http://<EXTERNAL-IP>:5000/employees
```

---

## Deployment Manual

Dacă preferi deployment pas cu pas fără Terraform:

### Windows (PowerShell)

```powershell
# Rulează scriptul de deployment
.\scripts\deploy_azure.ps1

# Sau cu parametri customizați
.\scripts\deploy_azure.ps1 `
  -ResourceGroup "MyRG" `
  -Location "westeurope" `
  -AcrName "myregistry"
```

### Linux/Mac (Bash)

```bash
# Dă permisiuni de execuție
chmod +x scripts/deploy_azure.sh

# Rulează scriptul
./scripts/deploy_azure.sh
```

**Scriptul va:**
1. ✅ Verifica prerequisites
2. ✅ Login Azure
3. ✅ Crea Resource Group
4. ✅ Crea Azure Container Registry
5. ✅ Build și push imagini Docker
6. ✅ Crea Cosmos DB
7. ✅ Crea AKS cluster
8. ✅ Deploy aplicația
9. ✅ Afișa URL-uri de acces

---

## CI/CD cu GitHub Actions

### Setup GitHub Actions

**Pas 1: Creează Azure Service Principal**

```bash
az ad sp create-for-rbac \
  --name "github-actions-employee-dw" \
  --role contributor \
  --scopes /subscriptions/<subscription-id>/resourceGroups/EmployeeDataWarehouse-RG \
  --sdk-auth
```

**Output (copiază tot JSON-ul):**
```json
{
  "clientId": "xxx",
  "clientSecret": "xxx",
  "subscriptionId": "xxx",
  "tenantId": "xxx",
  ...
}
```

**Pas 2: Adaugă GitHub Secrets**

1. Mergi la repo GitHub: `Settings` → `Secrets and variables` → `Actions`
2. Click `New repository secret`
3. Adaugă următoarele secrets:

| Secret Name | Value |
|------------|-------|
| `AZURE_CREDENTIALS` | JSON-ul complet de la Pas 1 |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID |
| `AZURE_TENANT_ID` | Tenant ID |

**Pas 3: Push Code pe GitHub**

```bash
git add .
git commit -m "Add Azure deployment configuration"
git push origin main
```

**Pas 4: Workflow-ul se activează automat**

GitHub Actions va rula automat:
1. Build și test imagini Docker
2. Push imagini în ACR
3. Deploy pe AKS
4. Run integration tests
5. Notify rezultat

**Vezi progresul:**
- GitHub repo → `Actions` tab
- Click pe workflow run

---

## Servicii Azure Utilizate

### 1. Azure Kubernetes Service (AKS)

**Ce face:**
- Orchestrează containerele Docker
- Auto-scaling
- Load balancing
- High availability

**Configurație:**
- Node VM: Standard_B2s (2 vCPU, 4GB RAM)
- Nodes: 2 (min: 1, max: 3)
- Auto-scaling: Activat
- Networking: Azure CNI

**Cost estimat:** ~70-100 USD/lună (cu auto-scaling la minim)

### 2. Azure Container Registry (ACR)

**Ce face:**
- Stocare imagini Docker private
- Integrare cu AKS
- Vulnerability scanning

**Configurație:**
- SKU: Basic
- Admin enabled: Yes
- Geo-replication: No

**Cost estimat:** ~5 USD/lună

### 3. Azure Cosmos DB for MongoDB API

**Ce face:**
- ÎNLOCUIEȘTE MongoDB local
- Database NoSQL managed
- Global distribution
- Auto-scaling
- 99.99% SLA

**Configurație:**
- API: MongoDB
- Tier: Free (400 RU/s, 5GB)
- Consistency: Session
- Multi-region: No (pentru cost redus)

**Cost estimat:** FREE (până la 400 RU/s)

### 4. Azure Load Balancer

**Ce face:**
- Distribuie trafic între pod-uri
- Public IP extern
- Health checks

**Cost estimat:** ~20 USD/lună

---

## Costuri și Optimizare

### Cost Total Estimat

| Serviciu | Cost/Lună | Note |
|----------|-----------|------|
| AKS Cluster | $70-100 | Depinde de uptime |
| ACR | $5 | Basic tier |
| Cosmos DB | $0 | Free tier |
| Load Balancer | $20 | Standard |
| Storage | $5 | Logs, volumes |
| **TOTAL** | **$100-130** | Cu optimizări |

### Optimizări pentru Cost Redus

**1. Folosește Azure Free Tier**
```bash
# La crearea Cosmos DB
az cosmosdb create ... --enable-free-tier true
```

**2. Auto-shutdown AKS când nu îl folosești**
```bash
# Stop AKS cluster
az aks stop --name employee-dw-aks --resource-group EmployeeDataWarehouse-RG

# Start când ai nevoie
az aks start --name employee-dw-aks --resource-group EmployeeDataWarehouse-RG
```

**3. Reduce node count**
```bash
# Scalează la 1 node când testezi
az aks scale --name employee-dw-aks \
  --resource-group EmployeeDataWarehouse-RG \
  --node-count 1
```

**4. Șterge când nu folosești**
```bash
# Șterge toate resursele
./scripts/cleanup_azure.sh
```

### Free Tier Azure

**Ce este FREE pentru totdeauna:**
- Cosmos DB: 400 RU/s, 5GB (1 account per subscription)
- 750 ore/lună de B1S VM (primele 12 luni)
- 5GB Blob Storage

**Credit pentru studenți:**
- $100 USD pentru studenți (fără card de credit)
- https://azure.microsoft.com/en-us/free/students/

---

## Monitorizare și Logs

### Kubernetes Logs

```bash
# Logs pentru Data Warehouse
kubectl logs -f deployment/data-warehouse -n employee-dw

# Logs pentru toate pod-urile
kubectl logs -f -l app=data-warehouse -n employee-dw

# Ultimele 100 linii
kubectl logs --tail=100 deployment/data-warehouse -n employee-dw

# Logs pentru pod specific
kubectl logs <pod-name> -n employee-dw
```

### AKS Dashboard

```bash
# Deschide Kubernetes dashboard
az aks browse \
  --resource-group EmployeeDataWarehouse-RG \
  --name employee-dw-aks
```

### Azure Portal Monitoring

1. Mergi la portal.azure.com
2. Resource Group: `EmployeeDataWarehouse-RG`
3. Click pe AKS cluster: `employee-dw-aks`
4. Sidebar: `Monitoring` → `Insights`

**Metrici disponibile:**
- CPU usage
- Memory usage
- Pod count
- Network traffic
- Request latency

### Application Insights (Opțional)

Pentru monitoring avansat:
```bash
# Instalează Application Insights agent
kubectl apply -f https://github.com/microsoft/Application-Insights-K8s-Codeless-Attach/releases/download/v1.0.0/application-insights-k8s-codeless-attach.yaml
```

---

## Troubleshooting

### Problema 1: AKS Pods nu pornesc

**Simptom:**
```bash
kubectl get pods -n employee-dw
# Output: ImagePullBackOff
```

**Soluție:**
```bash
# Verifică că AKS are acces la ACR
az aks update \
  --name employee-dw-aks \
  --resource-group EmployeeDataWarehouse-RG \
  --attach-acr employeedwregistry

# Verifică că imaginile există în ACR
az acr repository list --name employeedwregistry
```

### Problema 2: External IP rămâne `<pending>`

**Simptom:**
```bash
kubectl get service data-warehouse -n employee-dw
# EXTERNAL-IP: <pending>
```

**Soluție:**
```bash
# Așteaptă 3-5 minute
# Verifică events
kubectl describe service data-warehouse -n employee-dw

# Dacă persistă, re-creează service-ul
kubectl delete service data-warehouse -n employee-dw
kubectl apply -f kubernetes/datawarehouse-service.yaml -n employee-dw
```

### Problema 3: Cosmos DB connection failed

**Simptom:**
```bash
kubectl logs deployment/data-warehouse -n employee-dw
# Error: MongoServerError: Authentication failed
```

**Soluție:**
```bash
# Verifică secret-ul
kubectl get secret cosmosdb-connection -n employee-dw -o yaml

# Re-creează secret-ul
kubectl delete secret cosmosdb-connection -n employee-dw

COSMOS_CONN=$(az cosmosdb keys list \
  --name employee-dw-cosmosdb \
  --resource-group EmployeeDataWarehouse-RG \
  --type connection-strings \
  --query "connectionStrings[0].connectionString" -o tsv)

kubectl create secret generic cosmosdb-connection \
  --from-literal=connection-string="$COSMOS_CONN" \
  -n employee-dw

# Restart pods
kubectl rollout restart deployment/data-warehouse -n employee-dw
```

### Problema 4: Out of Memory (OOM)

**Simptom:**
```bash
kubectl get pods -n employee-dw
# Status: OOMKilled
```

**Soluție:**
```bash
# Crește memory limits
kubectl edit deployment data-warehouse -n employee-dw

# Modifică:
resources:
  limits:
    memory: "1Gi"  # Era 512Mi
```

### Problema 5: GitHub Actions fail

**Simptom:**
GitHub Actions workflow eșuează la "Azure Login"

**Soluție:**
1. Verifică că `AZURE_CREDENTIALS` secret este corect
2. Re-creează Service Principal:
```bash
az ad sp create-for-rbac \
  --name "github-actions-employee-dw" \
  --role contributor \
  --scopes /subscriptions/<sub-id>/resourceGroups/EmployeeDataWarehouse-RG \
  --sdk-auth
```
3. Actualizează secret-ul în GitHub

---

## Comenzi Utile

### AKS Management

```bash
# Verifică status cluster
az aks show \
  --name employee-dw-aks \
  --resource-group EmployeeDataWarehouse-RG

# Stop cluster (economisește bani)
az aks stop --name employee-dw-aks --resource-group EmployeeDataWarehouse-RG

# Start cluster
az aks start --name employee-dw-aks --resource-group EmployeeDataWarehouse-RG

# Scalare manuală
kubectl scale deployment data-warehouse --replicas=5 -n employee-dw

# Upgrade Kubernetes version
az aks upgrade \
  --name employee-dw-aks \
  --resource-group EmployeeDataWarehouse-RG \
  --kubernetes-version 1.28.0
```

### ACR Management

```bash
# Lista imagini
az acr repository list --name employeedwregistry

# Lista tag-uri pentru o imagine
az acr repository show-tags \
  --name employeedwregistry \
  --repository data-warehouse

# Șterge imagine veche
az acr repository delete \
  --name employeedwregistry \
  --image data-warehouse:old-tag
```

### Cosmos DB Management

```bash
# Obține connection string
az cosmosdb keys list \
  --name employee-dw-cosmosdb \
  --resource-group EmployeeDataWarehouse-RG \
  --type connection-strings

# Verifică throughput
az cosmosdb mongodb database throughput show \
  --account-name employee-dw-cosmosdb \
  --resource-group EmployeeDataWarehouse-RG \
  --name employee_warehouse

# Backup manual
az cosmosdb backup \
  --name employee-dw-cosmosdb \
  --resource-group EmployeeDataWarehouse-RG
```

---

## Cleanup - Ștergere Resurse

### Opțiunea 1: Cu Script

```bash
# Windows
.\scripts\cleanup_azure.sh

# Linux/Mac
./scripts/cleanup_azure.sh
```

### Opțiunea 2: Cu Terraform

```bash
cd terraform
terraform destroy
# Confirmă cu: yes
```

### Opțiunea 3: Manual

```bash
# Șterge tot resource group-ul (toate resursele)
az group delete \
  --name EmployeeDataWarehouse-RG \
  --yes \
  --no-wait
```

**ATENȚIE:** Această comandă șterge TOATE resursele din resource group!

---

## Concluzii - Cerințe Laborator 3 ✅

### 1. Cloud Provider - Azure ✅
- ✅ Utilizare Azure Kubernetes Service (AKS)
- ✅ Deployment complet pe cloud
- ✅ Servicii managed: ACR, Cosmos DB, Load Balancer

### 2. Infrastructure as Code (IaC) ✅
- ✅ Terraform configuration completă
- ✅ Reproducibil și versionat
- ✅ Automatizare provizionare infrastructură

### 3. CI/CD ✅
- ✅ GitHub Actions workflows
- ✅ Automated build, test, deploy
- ✅ Integration testing pe cloud

### 4. Migrare Proiect ✅
- ✅ Toate serviciile migrate pe AKS
- ✅ Docker images în ACR
- ✅ Funcționalitate completă păstrată

### 5. SGBD Cloud ✅
- ✅ MongoDB local → Azure Cosmos DB
- ✅ MongoDB API compatibility
- ✅ Managed service cu auto-scaling

---

## Resurse Adiționale

- **Azure Documentation:** https://docs.microsoft.com/azure/
- **AKS Best Practices:** https://docs.microsoft.com/azure/aks/best-practices
- **Cosmos DB MongoDB API:** https://docs.microsoft.com/azure/cosmos-db/mongodb/
- **Terraform Azure Provider:** https://registry.terraform.io/providers/hashicorp/azurerm/
- **GitHub Actions:** https://docs.github.com/actions

---

**Creat pentru:** PAD (Programarea Aplicațiilor Distribuite) - Laborator 3
**Status:** ✅ Production Ready
