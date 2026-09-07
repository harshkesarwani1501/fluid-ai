# Fluid AI DevOps Challenge — Runbook

Stack: Flask backend + Redis, on k3s (single EC2 node), deployed via GitHub
Actions with a self-hosted runner on that same box.

**Do all of Part A ahead of your 90-minute window.** The challenge is timed
from "start" to "submitted video" — you don't get graded on how long setup
took, only on the final quality and your debugging narration. Walking in
with a working cluster and a green pipeline, then spending your live time on
the *demo + intentional failure*, is the strong play.

---

## Part A — One-time setup (do this before your window starts)

### 1. Launch the EC2 instance
- Ubuntu 22.04, t3.medium (2 vCPU / 4GB is comfortable for k3s + 2 pods)
- Security group inbound: 22 (SSH), 30080 (NodePort, matches backend.yaml),
  6443 only if you want remote kubectl access from your laptop

### 2. Install k3s
```bash
curl -sfL https://get.k3s.io | sh -
sudo cat /etc/rancher/k3s/k3s.yaml   # kubeconfig
# to use kubectl as a non-root user:
mkdir -p ~/.kube && sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
kubectl get nodes   # confirm Ready
```

### 3. Install Docker (needed by the GitHub Actions runner to build images,
   even though deploy uses kubectl not docker directly)
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

### 4. Register a self-hosted GitHub Actions runner on this EC2 box
In your repo: Settings → Actions → Runners → New self-hosted runner → follow
the generated `./config.sh` commands, then:
```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

### 5. Add repo secrets
Settings → Secrets and variables → Actions:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN` (a Docker Hub access token, not your password)

### 6. Edit `k8s/backend.yaml`
Replace `YOUR_DOCKERHUB_USERNAME` with your real Docker Hub username.

### 7. First deploy (manual, to prove the base cluster works before wiring CI)
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/backend.yaml
kubectl get pods -w
curl http://<EC2_PUBLIC_IP>:30080/
curl http://<EC2_PUBLIC_IP>:30080/health
```

### 8. Push to `main` and confirm the Actions pipeline goes green
This proves build → push → auto-deploy end to end before you start recording.

---

## Part B — Your 90-minute / 8–12 min video window

### 1. Live Demo (3–4 min)
- `curl` the app a few times, show the hit counter incrementing
- `kubectl get pods,svc,deploy` — show everything Running/Ready
- Push a trivial change (e.g. change the `message` string) → show the
  Actions run live → show the pod rolling → `curl` again to prove the new
  version is serving

### 2. Architecture Walkthrough (2–3 min)
Talking points:
- Single k3s node on EC2 — real Kubernetes control plane + kubelet, not a
  managed abstraction
- Backend (Flask, 2 replicas) ↔ Redis (1 replica) ↔ NodePort Service exposing
  it externally
- CI/CD: GitHub-hosted runner builds & pushes the image; a self-hosted
  runner *on the cluster's node* does the actual `kubectl` deploy — keeps
  the k8s API off the public internet while still automating deploys
- Why NodePort and not a LoadBalancer/Ingress: single EC2 box, no cloud LB
  to attach, and it keeps the failure-domain small for a timed demo

### 3. Reliability Feature — Probes + Resource Limits (explain explicitly)
- **Why chosen:** cheapest-to-implement, highest-signal reliability
  primitive — it's what actually gates traffic and triggers self-healing
- **Problem it solves:** without readiness probes, k8s sends traffic to
  pods before they can actually serve (or after they've silently died
  inside); without resource limits, one noisy pod can starve its
  neighbours on a shared node
- **Tradeoff:** probes add real load (a hit every 5–10s per pod) and, if
  thresholds are too aggressive, can cause *false-positive restarts* under
  transient slowness — which is exactly what you're about to demonstrate
  on purpose in the next section
- Resource limits set too tight = OOMKilled or CPU-throttled pods; too
  loose = they stop protecting the node at all. It's a tuning tradeoff, not
  a free win.

### 4. Failure Debugging Walkthrough (2–3 min) — THE MAIN EVENT
Break it live:
```bash
kubectl set env deployment/backend-app REDIS_HOST=wrong-redis-host
```
Narrate as it unfolds:
```bash
kubectl get pods                 # watch restarts climb, CrashLoopBackOff appears
kubectl describe pod <pod-name>  # "Liveness probe failed: HTTP probe failed with statuscode: 500"
kubectl logs <pod-name>          # connection error to wrong-redis-host in app logs
```
- State your reasoning out loud: "Pods are restarting, not pending or
  failing to schedule — so it's not a resource/scheduling issue, it's
  something failing *after* the container starts. The liveness probe is
  failing, and /health only fails on a Redis connection error, so the
  fault is almost certainly the Redis connection, not the app code itself."
- Root cause: bad `REDIS_HOST` value.
- Fix:
```bash
kubectl set env deployment/backend-app REDIS_HOST=redis-service
kubectl rollout status deployment/backend-app
curl http://<EC2_PUBLIC_IP>:30080/health   # back to 200
```

### 5. Tradeoff Discussion (1–2 min)
What you simplified:
- Single-node cluster — no HA control plane, no multi-node scheduling story
- NodePort instead of Ingress + TLS — fine for a demo, not for real traffic
- Redis has no PersistentVolume — data is lost on pod restart
- No autoscaling (HPA) — fixed 2 replicas regardless of load
- Secrets (Docker Hub token) live in GitHub Actions secrets, not a vault
- Self-hosted runner is a single point of failure for the deploy step

What you'd change for real production:
- Multi-node managed cluster (EKS/GKE) with node autoscaling
- Ingress controller + cert-manager for TLS, real DNS
- Managed/replicated Redis (or ElastiCache) with persistence
- HPA on the backend based on CPU/RPS
- ArgoCD for GitOps instead of a runner doing `kubectl set image` by hand
- Centralized logging/metrics (you'd reach for Prometheus/Grafana/ELK here)

---

## Cleanup after recording
```bash
kubectl delete -f k8s/
sudo /usr/local/bin/k3s-uninstall.sh   # if you want to fully tear down k3s
```
Terminate the EC2 instance if you don't need it running afterward — no
point paying for an idle t3.medium.
