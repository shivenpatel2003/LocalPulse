"""
Infrastructure as Code.

This package contains infrastructure definitions:

- terraform/: Terraform configurations for GCP resources
- cloudbuild/: Cloud Build pipeline definitions
- k8s/: Kubernetes manifests (if using GKE)

Deployment targets:
- Google Cloud Run (primary)
- Neo4j Aura (managed graph database)
- Pinecone (managed vector database)
- Redis (Cloud Memorystore)
"""
