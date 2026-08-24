# DeployReady

This challenge is designed for associate-level DevOps candidates. It is intentionally harder than an entry-level deployment exercise and tests your ability to handle containerisation, automated pipelines, cloud deployment, and safe release practices end to end.

---

## 1. Business Context

**Client:** Kora Analytics
**Industry:** SaaS - Data dashboards for logistics companies

### The Problem

Every time the Kora team wants to deploy a new version of their app, a developer manually SSHs into the server, pulls the code, and restarts the process by hand. There are no automated tests before a release and no way to tell if a deploy broke something until a customer complains.

### Your Role

You are joining as their first DevOps engineer. The application code already works, and your job is to **containerise it, automate the delivery pipeline, and get it running on a cloud platform** (AWS, GCP, Azure, or any other cloud provider you are familiar with).

---

## 2. The Application

A simple Node.js API is provided in the [`app/`](./app/) directory. It has three endpoints:

| Method | Route      | Description                            |
| ------ | ---------- | -------------------------------------- |
| GET    | `/health`  | Returns `{ "status": "ok" }`           |
| GET    | `/metrics` | Returns uptime and memory usage        |
| POST   | `/data`    | Accepts a JSON body and echoes it back |

Run it locally:

```bash
cd app
npm install
npm start
```

Do not change the application logic. Your work is everything around it.

---

## 3. The Assignment

### Part 1 - Containerise the App

**Deliverables:** A `Dockerfile` and a `docker-compose.yml` in the root of your repository.

**Dockerfile requirements:**

- The app must run inside a Docker container.
- The container must accept a `PORT` environment variable.
- The container must **not** run as the `root` user.

**Docker Compose requirements:**

- Define the app as a service in `docker-compose.yml`.
- Map port `3000` on the host to the container.
- Pass the `PORT` variable via an `.env` file (include a `.env.example` with placeholder values).
- Running the following must start a working API:
  ```bash
  docker compose up --build
  ```

---

### Part 2 - Automate the Pipeline

**Deliverable:** A `.github/workflows/deploy.yml` GitHub Actions workflow.

The pipeline should test, build, push, deploy, and then verify the release with a health check on every push to `main`. If the health check fails, roll back to the previous image and fail the workflow.

Additional requirements:

- Secrets (SSH key, registry token) must be stored as **GitHub repository secrets**, never in the code.
- Add a short comment above each step in the YAML explaining what it does.

---

## 4. Monitoring and Observability

**Deliverable:** A short `OBSERVABILITY.md` or a clearly documented section in `DEPLOYMENT.md`.

Add a simple monitoring and observability setup for the deployed app so it is easy to tell when the service is unhealthy or behaving badly.

Requirements:

- Capture application logs in a way that makes them easy to review later.
- Add at least one health check, alert, or monitoring signal for the deployed service.
- Document how you would spot a failed deployment, a crash, or rising error rates.

---

### Part 3 - Deploy to the Cloud

**Deliverable:** A running service on a cloud platform and a short `DEPLOYMENT.md` explaining your setup.

Use **AWS, GCP, Azure, or any other cloud provider you are familiar with**. Provision the following (via the cloud console is fine):

- A **virtual machine** (e.g. AWS EC2 `t2.micro`, GCP `e2-micro`, Azure B1s) with Docker installed.
- A **firewall / security group** that allows:
  - HTTP on port 80 from anywhere
  - SSH on port 22 **from your IP only**, not open to the world
- A **service account / IAM user or role** for the pipeline with only the permissions it needs.

At submission time, `GET http://<your-server-ip>/health` must return `{ "status": "ok" }`.

Document in `DEPLOYMENT.md`:

- Which cloud provider and service you used, and why
- How you set up the virtual machine
- How you installed Docker and pulled your image
- How to check if the container is running
- How to view the application logs

---

## 5. Bonus (Optional)

Pick **one** of the following if you want to go further:

- **Use Terraform** (or your cloud's IaC tool) to provision the VM and firewall rules instead of the console.
- **Add a cloud monitoring alarm** (e.g. AWS CloudWatch, GCP Cloud Monitoring, Azure Monitor) that triggers if `/health` stops responding.
- **Implement a rollback step** in the pipeline that re-deploys the previous image if the health check fails after deploy.

Describe what you added and why in your `DEPLOYMENT.md`.

---

## 6. Submission Instructions

1. **Fork** this repository.
2. Complete all three parts in your fork.
3. **Replace this README** with your own documentation (architecture overview, setup steps, decisions made).
4. Submit your repo link via the [online form](https://forms.cloud.microsoft/e/f3FF83LVz3).

---

## ⚠️ Pre-Submission Checklist

- [ ] `docker compose up --build` starts the app locally
- [ ] A `.env.example` file is committed (the real `.env` is not)
- [ ] At least one successful pipeline run is visible in the GitHub Actions tab
- [ ] `GET /health` on your cloud server's public IP returns 200
- [ ] No secrets or `.pem` files committed to the repository
- [ ] SSH port 22 is **not** open to the world (`0.0.0.0/0`)
- [ ] `DEPLOYMENT.md` is present and covers the four points in Part 3
- [ ] `OBSERVABILITY.md` or the observability section in `DEPLOYMENT.md` explains monitoring and logging
- [ ] This README has been replaced with your own documentation
- [ ] Commit history shows progress over time (not a single upload commit)
