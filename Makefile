SHELL := /bin/zsh
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:
.DEFAULT_GOAL := help

UV ?= uv
TURSO ?= turso
DB ?= clipboard-snap
NAME ?= Clipboard Snap
ENDPOINT ?= https://DATABASE-ORG.turso.io/v2/pipeline
TOKEN_EXPIRATION ?= 90d
ID ?=
MAC_SOURCE ?= maccy-$(shell hostname -s)

DIST_DIR := dist
PRIVATE_DIR := private
XML := $(DIST_DIR)/$(NAME).xml
SHORTCUT := $(DIST_DIR)/$(NAME).shortcut
PRIVATE_NAME ?= Clipboard Snap Configured
PRIVATE_SHORTCUT := $(PRIVATE_DIR)/$(PRIVATE_NAME).shortcut
SKILL_DIR := skills/clipboard-snap-shortcut
SCRIPTS := $(SKILL_DIR)/scripts
SCHEMA := $(SKILL_DIR)/assets/schema.sql

.PHONY: help sync build validate lint check ci shortcut open clean \
	db db-url db-token db-verify db-latest db-record configured-shortcut \
	mac-token mac-push

help: ## Show available commands.
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install locked development dependencies with uv.
	$(UV) sync --locked

build: ## Generate the public, credential-free Shortcut plist.
	mkdir -p "$(DIST_DIR)"
	$(UV) run --frozen "$(SCRIPTS)/build_shortcut.py" \
		--name "$(NAME)" \
		--endpoint "$(ENDPOINT)" \
		--output "$(XML)"

validate: build ## Validate the generated action and credential contract.
	$(UV) run --frozen "$(SCRIPTS)/check_shortcut.py" "$(XML)"
	plutil -lint "$(XML)"

lint: ## Lint the Python build tools.
	$(UV) run --frozen ruff check "$(SCRIPTS)"

check: lint validate ## Run all local source and artifact checks.

ci: sync check ## Run the checks used by GitHub Actions.
	git diff --exit-code -- "$(XML)"

shortcut: validate ## Build and sign the public Shortcut on macOS.
	$(UV) run --frozen "$(SCRIPTS)/sign_shortcut.py" \
		"$(XML)" \
		--output "$(SHORTCUT)"

open: shortcut ## Open the public Shortcut in Apple Shortcuts.
	open "$(SHORTCUT)"

configured-shortcut: ## Build a private Shortcut with a fresh insert-only token.
	if [[ "$(ENDPOINT)" == "https://DATABASE-ORG.turso.io/v2/pipeline" ]]; then
		print -u2 "Set ENDPOINT to the database HTTP URL followed by /v2/pipeline"
		exit 2
	fi
	mkdir -p "$(PRIVATE_DIR)"
	temp_xml=$$(mktemp -t clipboard-snap-configured).xml
	trap 'rm -f "$$temp_xml"' EXIT
	TURSO_NO_UPDATE=1 "$(TURSO)" db tokens create "$(DB)" \
		-p clips:data_add --expiration "$(TOKEN_EXPIRATION)" | \
		$(UV) run --frozen "$(SCRIPTS)/build_shortcut.py" \
			--name "$(PRIVATE_NAME)" \
			--endpoint "$(ENDPOINT)" \
			--token-stdin \
			--patterns-file "$(CURDIR)/config.toml" \
			--output "$$temp_xml"
	$(UV) run --frozen "$(SCRIPTS)/sign_shortcut.py" \
		"$$temp_xml" \
		--allow-configured-token \
		--output "$(PRIVATE_SHORTCUT)"
	print "Private artifact: $(PRIVATE_SHORTCUT)"

db: ## Create the Turso database when needed and apply the schema.
	if ! "$(TURSO)" db show "$(DB)" >/dev/null 2>&1; then
		"$(TURSO)" db create "$(DB)"
	fi
	"$(TURSO)" db shell "$(DB)" < "$(SCHEMA)"

db-url: ## Print the database HTTP URL; append /v2/pipeline in Shortcuts.
	"$(TURSO)" db show "$(DB)" --http-url

db-token: ## Create a 90-day insert-only token for the clips table.
	"$(TURSO)" db tokens create "$(DB)" \
		-p clips:data_add --expiration "$(TOKEN_EXPIRATION)"

db-verify: ## Show the ten latest saved text previews.
	"$(TURSO)" db shell "$(DB)" \
		"SELECT id, created_at, source, substr(text, 1, 80) AS preview FROM clips ORDER BY id DESC LIMIT 10;"

db-latest: ## Show the complete latest database record.
	"$(TURSO)" db shell "$(DB)" \
		"SELECT id, created_at, source, text FROM clips ORDER BY id DESC LIMIT 1;"

db-record: ## Show one complete record; usage: make db-record ID=123.
	if [[ "$(ID)" != <-> ]]; then
		print -u2 "ID must be a positive integer"
		exit 2
	fi
	"$(TURSO)" db shell "$(DB)" \
		"SELECT id, created_at, source, text FROM clips WHERE id = $(ID);"

mac-token: ## Mint a per-Mac insert-only token and store it in Keychain (never a file).
	@TOKEN=$$("$(TURSO)" db tokens create "$(DB)" -p clips:data_add --expiration "$(TOKEN_EXPIRATION)"); \
	if [ -z "$$TOKEN" ]; then \
		print -u2 "mac-token: turso returned an empty token; nothing stored"; \
		exit 1; \
	fi; \
	security add-generic-password -a "$$USER" -s "clipboard-snap-$(MAC_SOURCE)" -w "$$TOKEN" -U; \
	print "Stored in Keychain service: clipboard-snap-$(MAC_SOURCE)"

mac-push: ## Push new plain-text Maccy clips into the shared clips table.
	scripts/push_maccy_clips.sh \
		--endpoint "$$($(TURSO) db show $(DB) --http-url)/v2/pipeline" \
		--keychain-service "clipboard-snap-$(MAC_SOURCE)" \
		--source "$(MAC_SOURCE)"

clean: ## Remove public generated artifacts and local Python caches.
	rm -f "$(XML)" "$(SHORTCUT)"
	rm -rf .ruff_cache .pytest_cache "$(SCRIPTS)/__pycache__"
