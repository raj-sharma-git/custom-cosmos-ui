# Cosmos DB UI Manager

<img width="2880" height="1614" alt="image" src="https://github.com/user-attachments/assets/aa203759-f199-4ee5-8dee-54b9f41acbe2" />


A lightweight, modern web interface for managing Azure Cosmos DB resources. This tool provides an easy-to-use dashboard to create, view, and delete databases and containers, as well as a bulk provisioning feature via CSV/Excel uploads.

## Use Cases

This application is designed to solve common challenges when working with secure, private Cosmos DB environments:

1. **Accessing Private Production Data:**
   Production Cosmos DB instances are often locked behind private Virtual Networks (VNets), completely blocking access from the public internet or even the Azure Portal. By deploying this lightweight Docker container directly into your Azure Kubernetes Service (AKS) cluster or an Azure Container App within the same VNet, you can securely access and interact with your production Cosmos DB data without exposing the database to the internet.

2. **Environment Data Replication (Dev to Prod):**
   When you need to replicate or update configurations/data from a Development environment to Production, doing it manually via scripts can be tedious. This tool allows you to export configurations and use the Bulk Provision (Excel/CSV) feature to rapidly replicate identical Database and Container structures across environments, ensuring parity between Dev and Prod safely from within your VNet.

## Features
- **Dashboard Overview:** View all connected Databases and Containers.
- **Bulk Provisioning:** Upload a CSV or Excel file to automatically create multiple databases and containers at once (with Merge and Overwrite capabilities).
- **CRUD Operations:** Easily create and securely delete Databases and Containers.
- **Light/Dark Mode:** Modern UI tailored to your preferences.

## Docker Deployment

This project includes a highly optimized Dockerfile using `python:3.12-alpine` and a multi-stage build process to ensure the smallest possible image footprint—perfect for deploying as a lightweight sidecar or standalone internal utility in AKS.

### 1. Build the Image
```bash
docker build -t cosmos-ui:latest .
```

### 2. Run the Container locally
```bash
docker run -p 8000:8000 cosmos-ui:latest
```

The application will be accessible at `http://localhost:8000`.

### 3. Deploying to AKS (Azure Kubernetes Service)
When deploying to AKS within your private VNet:
1. Push the built image to your internal Azure Container Registry (ACR) or You can pull it from dockerhub `https://hub.docker.com/r/dockercustom/cosmos-ui`
2. Create a Deployment mapping container port `5001`.
3. Expose the deployment via an internal LoadBalancer or ClusterIP service and add path /cosmos-ui in Ingress.
4. Ensure the AKS cluster's subnets have the necessary VNet peering or Service Endpoints configured to access the Cosmos DB private endpoint.
