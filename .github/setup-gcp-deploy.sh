#!/usr/bin/env bash
# deploy-backend.yml이 Cloud Run에 배포할 수 있도록 GCP 쪽을 1회 설정한다.
# - 배포 전용 서비스 계정(github-deployer)과 최소 권한
# - GitHub OIDC를 믿는 Workload Identity Pool/Provider (이 레포의 main 브랜치만 허용)
# 프로젝트 owner 계정으로 실행한다. 이미 있는 리소스는 건너뛴다.
set -euo pipefail

PROJECT_ID=fin-aily-us
PROJECT_NUMBER=437915204376
REPO=jonas-jun/fin-aily-us
SA_NAME=github-deployer
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"  # Cloud Run 런타임·Cloud Build SA
POOL=github
PROVIDER=fin-aily-us

gcloud services enable sts.googleapis.com iamcredentials.googleapis.com --project "$PROJECT_ID"

gcloud iam service-accounts describe "$SA" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT_ID" \
       --display-name "GitHub Actions Cloud Run deployer"

# 소스 배포(--source)에 필요한 최소 권한
for role in roles/run.sourceDeveloper roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${SA}" --role "$role" --condition=None --quiet >/dev/null
done
# 런타임·빌드 SA로 동작(actAs)할 권한
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT_ID" \
  --member "serviceAccount:${SA}" --role roles/iam.serviceAccountUser --quiet >/dev/null

gcloud iam workload-identity-pools describe "$POOL" --project "$PROJECT_ID" --location global >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools create "$POOL" --project "$PROJECT_ID" --location global \
       --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers describe "$PROVIDER" --project "$PROJECT_ID" \
    --location global --workload-identity-pool "$POOL" >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --project "$PROJECT_ID" \
       --location global --workload-identity-pool "$POOL" \
       --display-name "fin-aily-us repo" \
       --issuer-uri "https://token.actions.githubusercontent.com" \
       --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
       --attribute-condition "assertion.repository=='${REPO}' && assertion.ref=='refs/heads/main'"

gcloud iam service-accounts add-iam-policy-binding "$SA" --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO}" \
  --quiet >/dev/null

cat <<OUT
완료. GitHub 레포 Variables(Settings > Secrets and variables > Actions > Variables)에 등록한다:
  GCP_WIF_PROVIDER = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}
  GCP_DEPLOY_SA    = ${SA}
OUT
