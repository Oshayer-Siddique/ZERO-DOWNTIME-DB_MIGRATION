# Zero-Downtime Database Migration Pipeline

## System Architecture

```mermaid
flowchart LR

A[Developer] --> B[GitHub Repository]

B --> C[GitHub Actions CI Pipeline]


subgraph CI["CI/CD Pipeline"]

C --> D[SQL Migration Safety Check]

D --> E[Migration Test]

end


subgraph ENV["Docker Compose Environment"]

E --> F[FastAPI Application]

E --> G[PostgreSQL Database]

end


subgraph APP["Application Versions"]

F --> H[API v1<br/>Legacy Schema<br/>full_name]

F --> I[API v2<br/>New Schema<br/>first_name + last_name]

end


subgraph MIG["Zero Downtime Migration"]

G --> J[Expand<br/>Add New Columns]

J --> K[Backfill + Dual Write]

K --> L[Contract<br/>Remove Old Column]

end


L --> M[Validated Migration]

H --> M

I --> M
