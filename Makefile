# Homelab deploy (thenetwork k3s)

.PHONY: homelab-sync homelab-deploy homelab-bootstrap-db homelab-secrets homelab-smtp homelab-maps homelab-status

HOMELAB_HOST ?= user@your-server
HOMELAB_DEST ?= /home/dad/job-platform

homelab-sync:
	./deploy/scripts/sync-and-deploy.sh

homelab-deploy: homelab-sync

homelab-bootstrap-db:
	ssh -F /dev/null $(HOMELAB_HOST) 'cd $(HOMELAB_DEST) && ./deploy/scripts/bootstrap-database.sh'

homelab-secrets:
	@test -n "$(JOBS_PLATFORM_DB_PASSWORD)" || (echo "Set JOBS_PLATFORM_DB_PASSWORD"; exit 1)
	ssh -F /dev/null $(HOMELAB_HOST) 'cd $(HOMELAB_DEST) && JOBS_PLATFORM_DB_PASSWORD=$(JOBS_PLATFORM_DB_PASSWORD) ./deploy/scripts/init-homelab-secrets.sh'

homelab-smtp:
	chmod +x ./deploy/scripts/sync-smtp-from-gcp.sh
	./deploy/scripts/sync-smtp-from-gcp.sh

homelab-maps:
	chmod +x ./deploy/scripts/setup-google-maps-gcp.sh ./deploy/scripts/sync-google-maps-from-gcp.sh
	./deploy/scripts/setup-google-maps-gcp.sh
	./deploy/scripts/sync-google-maps-from-gcp.sh

homelab-status:
	ssh -F /dev/null $(HOMELAB_HOST) 'export KUBECONFIG=$$HOME/.kube/config; kubectl get pods,svc,cronjob -n jobs-platform'
