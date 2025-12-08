# Azure Quick Start - 30 Minute Deployment

## Employee Data Warehouse pe Azure - Ghid Rapid

Acest ghid te ajută să deployment-ezi sistemul Employee Data Warehouse pe Azure în **30 de minute**.

---

## Pregătire (5 minute)

### 1. Instalează Azure CLI

**Windows:**
```powershell
winget install -e --id Microsoft.AzureCLI
```

**Sau descarcă:** https://aka.ms/installazurecliwindows

### 2. Verifică Instalarea

```bash
az --version
```

### 3. Login Azure

```bash
az login
```

Browser-ul se va deschide - autentifică-te cu contul Azure.

---

## Deployment Rapid cu Script (20 minute)

### Windows (PowerShell)

```powershell
# Navighează în directorul proiectului
cd C:\Users\ciprian.panzaru\Desktop\PAD\laborator_3

# Rulează scriptul de deployment
.\scripts\deploy_azure.ps1
```

### Linux/Mac (Bash)

```bash
# Navighează în directorul proiectului
cd /c/Users/ciprian.panzaru/Desktop/PAD/laborator_3

# Dă permisiuni
chmod +x scripts/deploy_azure.sh

# Rulează scriptul
./scripts/deploy_azure.sh
```

**Scriptul va crea automat:**
1. Resource Group
2. Azure Container Registry
3. Azure Cosmos DB (free tier)
4. AKS Cluster (2 nodes)
5. Deploy aplicația

**Timp așteptare:** ~20 minute (AKS cluster crearea durează cel mai mult)

---

## Verificare Deployment (2 minute)

```bash
# Verifică pod-urile
kubectl get pods -n employee-dw

# Verifică serviciile
kubectl get services -n employee-dw

# Obține URL-ul public
kubectl get service data-warehouse -n employee-dw
```

**Copiază EXTERNAL-IP și testează:**

```bash
# Test health check
curl http://<EXTERNAL-IP>:5000/health

# Test API
curl http://<EXTERNAL-IP>:5000/employees
```

---

## Test Complet în Postman (3 minute)

1. Deschide Postman
2. Importă colecția: `postman/Employee_DataWarehouse.postman_collection.json`
3. Editează variabila `base_url` → `http://<EXTERNAL-IP>:5000`
4. Rulează toate testele

---

## Opțional: Setup CI/CD cu GitHub Actions

### Pas 1: Creează Service Principal

```bash
az ad sp create-for-rbac \
  --name "github-actions-employee-dw" \
  --role contributor \
  --scopes /subscriptions/$(az account show --query id -o tsv)/resourceGroups/EmployeeDataWarehouse-RG \
  --sdk-auth
```

**Copiază tot JSON-ul returnat.**

### Pas 2: Adaugă GitHub Secret

1. GitHub repo → Settings → Secrets and variables → Actions
2. New repository secret
3. Name: `AZURE_CREDENTIALS`
4. Value: JSON-ul de la Pas 1
5. Add secret

### Pas 3: Push Code

```bash
git add .
git commit -m "Add Azure deployment"
git push origin main
```

GitHub Actions va rula automat deployment!

---

## Cleanup (Ștergere Resurse)

Când ai terminat testele:

```bash
# Windows
.\scripts\cleanup_azure.sh

# Linux/Mac
./scripts/cleanup_azure.sh
```

Sau manual:

```bash
az group delete --name EmployeeDataWarehouse-RG --yes --no-wait
```

---

## Troubleshooting Rapid

### Pods nu pornesc

```bash
# Verifică logs
kubectl logs deployment/data-warehouse -n employee-dw

# Restart
kubectl rollout restart deployment/data-warehouse -n employee-dw
```

### External IP rămâne `<pending>`

```bash
# Așteaptă 3-5 minute
kubectl get service data-warehouse -n employee-dw -w
```

### Cosmos DB connection error

```bash
# Re-creează secret-ul
COSMOS_CONN=$(az cosmosdb keys list --name employee-dw-cosmosdb --resource-group EmployeeDataWarehouse-RG --type connection-strings --query "connectionStrings[0].connectionString" -o tsv)

kubectl delete secret cosmosdb-connection -n employee-dw
kubectl create secret generic cosmosdb-connection --from-literal=connection-string="$COSMOS_CONN" -n employee-dw

kubectl rollout restart deployment/data-warehouse -n employee-dw
```

---

## Costuri

- **AKS:** ~$70-100/lună (stop când nu folosești!)
- **ACR:** ~$5/lună
- **Cosmos DB:** FREE (free tier)
- **Load Balancer:** ~$20/lună

**Total estimat:** $100-130/lună

**Economisește:**
```bash
# Stop AKS când nu îl folosești
az aks stop --name employee-dw-aks --resource-group EmployeeDataWarehouse-RG

# Start când ai nevoie
az aks start --name employee-dw-aks --resource-group EmployeeDataWarehouse-RG
```

---

## Resurse

- **Documentație completă:** [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md)
- **Terraform (IaC):** `terraform/` directory
- **GitHub Actions:** `.github/workflows/`

---

**Succes la deployment!** 🚀
