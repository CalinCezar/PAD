# Ghid de Utilizare - Employee Data Warehouse

## Descriere Generală

Acest proiect implementează un **sistem distribuit de tip data warehouse** pentru managementul datelor despre angajați. Sistemul demonstrează utilizarea pattern-urilor avansate de arhitectură software:

- ✅ **Circuit Breaker** - Prevenirea cascadării erorilor
- ✅ **Rate Limiting** - Limitarea numărului de cereri
- ✅ **Timeout** - Prevenirea blocării cererilor
- ✅ **Thread-Per-Request** - Procesare concurentă thread-safe

## Cerințe Sistem

### Software Necesar
- **Docker Desktop** - pentru containerizare
- **Python 3.10+** - pentru scripturi
- **Git Bash** (Windows) sau Terminal (Linux/Mac)
- **Postman** (opțional) - pentru testare API

### Verificare Instalare
```bash
docker --version        # Trebuie să returneze versiunea Docker
docker-compose --version
python --version        # Trebuie să fie 3.10 sau superior
```

## Pornire Rapidă (5 Minute)

### Pasul 1: Pornește Serviciile

**Pe Windows (PowerShell):**
```powershell
# Navighează în directorul proiectului
cd C:\Users\ciprian.panzaru\Desktop\PAD\laborator_3

# Pornește serviciile
docker-compose up -d --build
```

**Pe Windows (Git Bash):**
```bash
cd /c/Users/ciprian.panzaru/Desktop/PAD/laborator_3
docker-compose up -d --build
```

### Pasul 2: Verifică că Serviciile Funcționează

Așteaptă ~30 secunde, apoi:

```bash
# Verifică containerele
docker-compose ps

# Trebuie să vezi 4 servicii running:
# - employee-mongodb
# - employee-json-node
# - employee-xml-node
# - employee-data-warehouse
```

### Pasul 3: Testează API-ul

**Test Quick:**
```bash
curl http://localhost:5000/health
```

Răspuns așteptat:
```json
{
  "status": "healthy",
  "service": "data-warehouse",
  "timestamp": "2025-12-07T12:00:00"
}
```

**Obține toți angajații:**
```bash
curl http://localhost:5000/employees
```

### Pasul 4: Adaugă Date de Test (Opțional)

```bash
# Instalează dependențele Python
pip install requests

# Rulează scriptul de seed
python scripts/seed_data.py
```

### Pasul 5: Rulează Suite-ul de Teste

```bash
python scripts/test_endpoints.py
```

## Arhitectura Sistemului

```
┌─────────────────────┐
│   Client (Postman)  │
│    sau Browser      │
└──────────┬──────────┘
           │ HTTP REST API
           ▼
┌─────────────────────────────────────┐
│    Data Warehouse (Port 5000)       │
│  ✓ Rate Limiting: 10 req/min        │
│  ✓ Timeout: 5-10 secunde            │
│  ✓ Circuit Breaker                  │
│  ✓ Thread-safe                      │
└──────┬────────────────────┬─────────┘
       │                    │
       │ Circuit Breaker    │ Circuit Breaker
       │ Protected          │ Protected
       ▼                    ▼
┌──────────────┐    ┌──────────────┐
│  JSON Node   │    │   XML Node   │
│  Port: 5001  │    │  Port: 5002  │
│              │    │              │
│ Date JSON    │    │ Date XML     │
│ Angajați 1-3 │    │ Angajați 4-6 │
└──────────────┘    └──────────────┘

┌─────────────────────────────────────┐
│     MongoDB (NoSQL Database)        │
│  - Port: 27017                      │
│  - Baza: employee_warehouse         │
│  - Colecție: employees              │
└─────────────────────────────────────┘
```

## Endpoint-uri API Disponibile

### Data Warehouse (localhost:5000)

#### 1. GET /employees - Obține toți angajații
```bash
# Toți angajații
curl http://localhost:5000/employees

# Cu paginare
curl "http://localhost:5000/employees?offset=0&limit=3"
```

#### 2. GET /employee?id=X - Obține un angajat specific
```bash
curl "http://localhost:5000/employee?id=1"
```

Răspuns:
```json
{
  "id": "1",
  "name": "John Doe",
  "position": "Software Engineer",
  "department": "Engineering",
  "salary": 75000,
  "email": "john.doe@company.com"
}
```

#### 3. PUT /employee - Creează sau actualizează angajat
```bash
curl -X PUT http://localhost:5000/employee \
  -H "Content-Type: application/json" \
  -d '{
    "id": "99",
    "name": "Test Angajat",
    "position": "Developer",
    "department": "IT",
    "salary": 70000,
    "email": "test@company.com"
  }'
```

#### 4. POST /employee - Modifică angajat existent
```bash
curl -X POST http://localhost:5000/employee \
  -H "Content-Type: application/json" \
  -d '{
    "id": "1",
    "salary": 85000
  }'
```

#### 5. DELETE /employee?id=X - Șterge angajat
```bash
curl -X DELETE "http://localhost:5000/employee?id=99"
```

#### 6. GET /health - Verificare stare serviciu
```bash
curl http://localhost:5000/health
```

#### 7. GET /circuit-breakers - Status Circuit Breaker
```bash
curl http://localhost:5000/circuit-breakers
```

## Testare Pattern-uri de Design

### 1. Rate Limiting (Limitare Rate)

Trimite 11 cereri rapide pentru a activa limitarea:

```bash
# Pe Windows (PowerShell)
for ($i=1; $i -le 11; $i++) {
    curl http://localhost:5000/health
}

# Pe Linux/Mac/Git Bash
for i in {1..11}; do
    curl http://localhost:5000/health
done
```

La a 11-a cerere vei primi:
```json
{
  "error": "Rate limit exceeded",
  "limit": 10,
  "window": 60
}
```

**Status Code**: 429 (Too Many Requests)

### 2. Circuit Breaker

**Pasul 1**: Oprește un nod pentru a simula o eroare:
```bash
docker stop employee-json-node
```

**Pasul 2**: Fă 6 cereri pentru a activa circuit breaker-ul:
```bash
for i in {1..6}; do
    curl http://localhost:5000/update/employees
    sleep 1
done
```

**Pasul 3**: Verifică statusul:
```bash
curl http://localhost:5000/circuit-breakers
```

Răspuns așteptat:
```json
{
  "json_node": {
    "state": "OPEN",
    "failures": 5,
    "last_failure": "2025-12-07T12:30:00"
  }
}
```

**Pasul 4**: Repornește nodul:
```bash
docker start employee-json-node
```

Așteaptă 60 secunde și circuit breaker-ul se va închide automat.

### 3. Timeout

Timeout-ul este configurat automat pe toate endpoint-urile (5-10 secunde).
Dacă un request durează mai mult, va returna:

```json
{"error": "Request timeout"}
```

**Status Code**: 504 (Gateway Timeout)

### 4. Thread-Per-Request (Procesare Concurentă)

Toate cererile sunt procesate concurent în mod thread-safe. Testează cu Apache Bench:

```bash
# Instalează Apache Bench
# Windows: Descarcă de la https://www.apachelounge.com/
# Linux: sudo apt-get install apache2-utils
# Mac: brew install httpd

# Trimite 100 cereri cu 10 concurente
ab -n 100 -c 10 http://localhost:5000/employees
```

## Testare cu Postman

### Importare Colecție

1. Deschide **Postman**
2. Click pe **Import**
3. Selectează fișierul: `postman/Employee_DataWarehouse.postman_collection.json`
4. Click **Import**

### Configurare Environment

1. Click pe **Environments**
2. Creează environment nou: "Employee DW Local"
3. Adaugă variabilele:
   - `base_url`: http://localhost:5000
   - `json_node_url`: http://localhost:5001
   - `xml_node_url`: http://localhost:5002

### Scenarii de Test

Colecția Postman include 40+ teste organizate în:

1. **Health Checks** - Verificare stare servicii
2. **Get Employees** - Obținere angajați (cu/fără paginare)
3. **Get Employee by ID** - Căutare după ID
4. **Create Employee (PUT)** - Creare angajați noi
5. **Update Employee (POST)** - Modificare angajați
6. **Delete Employee** - Ștergere angajați
7. **Data Synchronization** - Sincronizare între noduri
8. **Circuit Breaker** - Test circuit breaker
9. **Rate Limiting Test** - Test limitare rate (11 cereri)
10. **Node Operations** - Operații directe pe noduri

Vezi [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md) pentru ghid detaliat.

## Date de Test Inițiale

Sistemul vine pre-configurat cu 6 angajați:

### JSON Node (Angajați 1-3)
1. **John Doe** - Software Engineer, Engineering, $75,000
2. **Jane Smith** - Product Manager, Product, $85,000
3. **Bob Johnson** - DevOps Engineer, Operations, $80,000

### XML Node (Angajați 4-6)
4. **Alice Williams** - Data Scientist, Analytics, $90,000
5. **Charlie Brown** - UX Designer, Design, $70,000
6. **Diana Prince** - Security Engineer, Security, $95,000

## Comenzi Utile Docker

### Verificare Status
```bash
# Vezi toate containerele
docker-compose ps

# Statistici resurse
docker stats

# Verifică rețeaua
docker network ls
```

### Vizualizare Loguri
```bash
# Toate serviciile
docker-compose logs -f

# Un singur serviciu
docker-compose logs -f data-warehouse

# Ultimele 50 linii
docker-compose logs --tail=50 data-warehouse
```

### Restart Servicii
```bash
# Restart complet
docker-compose restart

# Restart un serviciu
docker-compose restart data-warehouse
```

### Oprire și Curățare
```bash
# Oprește serviciile
docker-compose down

# Oprește și șterge volumele (date MongoDB)
docker-compose down -v

# Oprește și șterge imaginile
docker-compose down --rmi all
```

## Deploy Kubernetes (Avansat)

### Cerințe
- Minikube sau alt cluster Kubernetes
- kubectl instalat

### Pornire

```bash
# Pornește Minikube
minikube start

# Deploy aplicația
./scripts/start_k8s.sh

# Verifică pods
kubectl get pods

# Verifică servicii
kubectl get services

# Accesează Data Warehouse
minikube service data-warehouse
```

### Scalare

```bash
# Scalează Data Warehouse la 5 replici
kubectl scale deployment data-warehouse --replicas=5

# Scalează nodurile
kubectl scale deployment json-node --replicas=3
kubectl scale deployment xml-node --replicas=3
```

### Oprire

```bash
./scripts/stop_k8s.sh
```

## Rezolvare Probleme

### Problema: Docker nu pornește

**Soluție**:
1. Pornește Docker Desktop
2. Verifică: `docker info`

### Problema: Port-ul 5000 este ocupat

**Soluție**:
```bash
# Windows - verifică ce folosește portul
netstat -ano | findstr :5000

# Oprește procesul sau schimbă portul în docker-compose.yml
```

### Problema: Serviciile nu sunt healthy

**Soluție**:
```bash
# Vezi logurile
docker-compose logs -f

# Restart servicii
docker-compose restart

# Rebuild complet
docker-compose down
docker-compose up -d --build
```

### Problema: MongoDB connection error

**Soluție**:
```bash
# Verifică MongoDB rulează
docker ps | grep mongodb

# Verifică logurile MongoDB
docker-compose logs mongodb

# Restart MongoDB
docker-compose restart mongodb
```

## Structura Fișierelor Proiect

```
laborator_3/
├── data_warehouse/         # Serviciul Data Warehouse
│   ├── app.py             # Aplicația Flask principală
│   └── Dockerfile         # Imaginea Docker
├── json_node/             # Nodul JSON
│   ├── app.py             # Serviciu date JSON
│   └── Dockerfile
├── xml_node/              # Nodul XML
│   ├── app.py             # Serviciu date XML
│   └── Dockerfile
├── kubernetes/            # Configurări Kubernetes (9 fișiere)
├── scripts/               # Scripturi utilitate
│   ├── seed_data.py       # Adaugă date test
│   ├── test_endpoints.py  # Testare API
│   ├── start_docker.sh    # Pornire Docker (Linux/Mac)
│   ├── start_docker.ps1   # Pornire Docker (Windows)
│   └── ...
├── postman/               # Colecție Postman
├── docker-compose.yml     # Orchestrare Docker
├── requirements.txt       # Dependențe Python
├── README.md             # Documentație completă
├── QUICKSTART.md         # Ghid rapid
├── POSTMAN_GUIDE.md      # Ghid testare Postman
└── GHID_UTILIZARE.md     # Acest fișier
```

## Performanță

### Caracteristici Performanță
- **Throughput**: 100+ req/s (limitat de rate limiting)
- **Latență**: < 100ms per request (local)
- **Cereri Concurente**: 50+ simultan
- **Capacitate**: Limitată de MongoDB

### Resurse Utilizate

**Per Serviciu**:
- CPU: 100-500m
- Memorie: 128-512Mi

**MongoDB**:
- CPU: 250-500m
- Memorie: 256-512Mi
- Disk: 1GB

## Securitate

### Implementat ✅
- Rate limiting per IP
- Validare input
- Operații thread-safe
- Circuit breaker protection
- Timeout protection

### Lipsă (TODO pentru Producție) ❌
- Autentificare/Autorizare
- HTTPS/TLS
- API keys
- Request signing

## Resurse Ajutor

- **Documentație Completă**: [README.md](README.md)
- **Ghid Rapid**: [QUICKSTART.md](QUICKSTART.md)
- **Testare Postman**: [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md)
- **Sumar Proiect**: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)

## Contact și Suport

Pentru întrebări sau probleme:
1. Verifică documentația
2. Caută în [README.md](README.md) secțiunea Troubleshooting
3. Verifică logurile: `docker-compose logs -f`

---

**Succes la testare!** 🚀

**Creat pentru**: PAD (Programarea Aplicațiilor Distribuite) - Laborator 3
