SHELL := /bin/zsh
.DEFAULT_GOAL := help

# Absolute path to this skill directory, however make was invoked. Kept simple
# for GNU Make 3.81 (macOS default): no .ONESHELL, one shell per recipe line.
SKILL_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
LAUNCHD   := $(SKILL_DIR)/scripts/launchd.sh
RUNNER    := $(SKILL_DIR)/scripts/triage_cron.sh
LOG       := $(SKILL_DIR)/triage_cron.log
WINDOW    ?=

.PHONY: help install uninstall start stop status run logs

help: ## Show available commands.
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Write the launchd plist and load it (hourly + once now). INTERVAL=3600.
	@INTERVAL=$(INTERVAL) /bin/zsh "$(LAUNCHD)" install

uninstall: ## Unload the launchd agent and remove its plist.
	@/bin/zsh "$(LAUNCHD)" uninstall

start: ## Kick off one run immediately via launchd.
	@/bin/zsh "$(LAUNCHD)" start

stop: ## Stop the currently running invocation (schedule stays installed).
	@/bin/zsh "$(LAUNCHD)" stop

status: ## Show whether the agent is loaded and the last log lines.
	@/bin/zsh "$(LAUNCHD)" status

run: ## Run one triage pass now in the foreground (no launchd); make run WINDOW=6h.
	@/bin/zsh "$(RUNNER)" $(WINDOW); tail -n 5 "$(LOG)" 2>/dev/null || true

logs: ## Follow the runner log.
	@touch "$(LOG)"; tail -f "$(LOG)"
