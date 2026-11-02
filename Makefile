# Gateway lifecycle, one gateway at a time: make deploy-litellm, make stop-litellm, ...
# Terraform still asks for confirmation on apply and destroy.

PROJECT  := my-gcp-project
REGION   := europe-west1
GATEWAYS := litellm bifrost kong
UI_PORT  := 4000

# Paths from this file, so make -C / -f work from anywhere.
ROOT     := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
BACKEND  := $(ROOT)/foundation/terraform/backend.hcl
tf_dir    = $(ROOT)/gateways/$*/terraform
tf        = terraform -chdir=$(tf_dir)

# Shell snippet: sets $db to the stack's Cloud SQL instance, or "" if the stack
# has none. Any Terraform error stops the recipe instead of reading as "no database".
find_db   = list=$$($(tf) state list) || exit 1; db=""; \
            if echo "$$list" | grep -q '^google_sql_database_instance\.'; then \
              db=$$($(tf) output -raw database_instance) || exit 1; \
            fi

.PHONY: help
help:
	@echo "Targets, for <gw> in: $(GATEWAYS)"
	@echo "  plan-<gw>     terraform plan"
	@echo "  deploy-<gw>   terraform apply"
	@echo "  stop-<gw>     stop the gateway's database (no compute charges, storage still billed; the gateway can't start)"
	@echo "  start-<gw>    start the database again (needed before plan, deploy and destroy)"
	@echo "  status-<gw>   gateway URL and database state"
	@echo "  ui-<gw>       proxy the gateway to http://localhost:$(UI_PORT) with your ID token (API/curl here; UI: run the proxy on your laptop)"
	@echo "  destroy-<gw>  terraform destroy (end of phase)"
	@echo "Kong only (config lives in Postgres, synced by decK from gateways/kong/config/kong.yaml; ADR 0015):"
	@echo "  diff-kong     live config vs kong.yaml (exit 2 if they differ)"
	@echo "  sync-kong     make the live config match kong.yaml"

# Pattern rules can't be .PHONY; this guard rejects unknown gateways instead,
# and .SECONDARY stops make treating check-*/init-*/running-*/callers-off-* as files to clean up.
.SECONDARY:

check-%:
	@$(if $(filter $*,$(GATEWAYS)),,$(error unknown gateway '$*'; one of: $(GATEWAYS)))
	@test -f $(BACKEND) || { echo "missing $(BACKEND); see backend.hcl.example"; exit 1; }
	@test -f $(tf_dir)/terraform.tfvars || { echo "missing $(tf_dir)/terraform.tfvars; copy terraform.tfvars.example"; exit 1; }

init-%: check-%
	@$(tf) init -input=false -backend-config=$(BACKEND) >/dev/null

# Terraform can't refresh or delete the database's user and contents while the
# instance is stopped, and a new revision can't start without it.
running-%: init-%
	@$(find_db); test -z "$$db" && exit 0; \
	policy=$$(gcloud sql instances describe "$$db" --project $(PROJECT) --format='value(settings.activationPolicy)') || exit 1; \
	test "$$policy" = ALWAYS || { echo "$$db is stopped: run make start-$* first"; exit 1; }

plan-%: running-%
	$(tf) plan

deploy-%: running-%
	$(tf) apply

# The agent and the harness job must not be left pointing at a gateway that is
# about to go: they would fail on its deleted key secret (agw-<gw>-...) or URL.
# A caller that doesn't exist (e.g. harness/ torn down) can't point at it.
caller_env = found=1; out=$$(gcloud run $(1) describe $(2) --project $(PROJECT) --region $(REGION) \
	  --format='value($(3))' 2>&1) || { \
	  case "$$out" in *NOT_FOUND*|*"Cannot find"*|*"could not be found"*) found=0; out="";; \
	  *) echo "could not read $(2)'s settings: $$out"; exit 1;; esac; }; \
	if [ $$found = 0 ]; then echo "note: $(2) not found, skipping"; \
	elif [ -z "$$out" ]; then echo "$(2) has no env vars: the gcloud format path is wrong, not checking blind"; exit 1; fi; \
	case "$$out" in *"$$url"*|*"agw-$*-"*) \
	  echo "$(2) still uses $*: $(4), apply it, then retry"; exit 1;; esac

callers-off-%: init-%
	@list=$$($(tf) state list) || exit 1; \
	echo "$$list" | grep -q '^google_cloud_run_v2_service\.' || exit 0; \
	url=$$($(tf) output -raw url) || exit 1; \
	$(call caller_env,services,agw-agent,spec.template.spec.containers[0].env,set agent/ back to target = "direct" with no gateway_url or gateway_api_key_secret); \
	$(call caller_env,jobs,agw-harness,spec.template.spec.template.spec.containers[0].env,clear gateway_url and gateway_api_key_secret in harness/)

destroy-%: running-% callers-off-%
	$(tf) destroy

stop-%: init-%
	@$(find_db); test -n "$$db" || { echo "$*: no database in this stack"; exit 0; }; \
	gcloud sql instances patch "$$db" --activation-policy=NEVER --project $(PROJECT) --quiet

start-%: init-%
	@$(find_db); test -n "$$db" || { echo "$*: no database in this stack"; exit 0; }; \
	gcloud sql instances patch "$$db" --activation-policy=ALWAYS --project $(PROJECT) --quiet

status-%: init-%
	@echo "url:      $$($(tf) output -raw url 2>/dev/null || echo 'not deployed')"
	@$(find_db); test -z "$$db" || echo "database: $$db $$(gcloud sql instances describe "$$db" --project $(PROJECT) --format='value(state,settings.activationPolicy)')"
	@if [ "$*" = kong ] && $(tf) output -raw url >/dev/null 2>&1; then \
	  echo "config:   decK diff against gateways/kong/config/kong.yaml (needs the database running)"; \
	  rc=0; out=$$($(ROOT)/gateways/kong/deck.sh diff 2>&1) || rc=$$?; \
	  case $$rc in 0|2) echo "$$out" | grep -A3 '^Summary' ;; *) echo "$$out"; echo "decK diff failed (exit $$rc)"; exit 1 ;; esac; \
	fi

ui-%: check-%
	@echo "http://localhost:$(UI_PORT) on this machine, for curl and scripts (the admin UI breaks behind code-server's port forwarding: see gateways/$*/README.md). Ctrl-C to stop."
	gcloud run services proxy agw-$* --project $(PROJECT) --region $(REGION) --port $(UI_PORT)

# Kong keeps its config in Postgres; decK applies gateways/kong/config/kong.yaml
# through the /admin-api route. Both need the database running.
.PHONY: diff-kong sync-kong
diff-kong: running-kong
	$(ROOT)/gateways/kong/deck.sh diff

sync-kong: running-kong
	$(ROOT)/gateways/kong/deck.sh sync
