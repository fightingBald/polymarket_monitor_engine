SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help bootstrap build lint format test test-integration ci-test run docs release gen migrate-up migrate-down

help:
	@echo ""
	@echo "Available targets:"
	@awk -F':|##' '/^[a-zA-Z0-9_-]+:.*##/{printf "  %-20s %s\n", $$1, $$NF}' $(MAKEFILE_LIST) | sort
	@echo ""

bootstrap: ## Install or update local tooling and dependencies
	@bash scripts/bootstrap.sh

build: ## Compile or validate build artifacts
	@bash scripts/build.sh

lint: ## Run static analysis and format checks
	@bash scripts/lint.sh

format: ## Automatically format source code
	@bash scripts/format.sh

test: ## Execute the fast unit test suite
	@bash scripts/test.sh

test-integration: ## Execute integration test suite
	@bash scripts/test-integration.sh

ci-test: ## Run the CI-equivalent test pipeline
	@bash scripts/ci-test.sh

run: ## Launch the primary service or application locally
	@bash scripts/run.sh

docs: ## Build or validate documentation artifacts
	@bash scripts/docs.sh

gen: ## Generate code from API/schema definitions
	@bash scripts/gen.sh

migrate-up: ## Apply database migrations
	@bash scripts/migrate-up.sh

migrate-down: ## Roll back database migrations
	@bash scripts/migrate-down.sh

release: ## Bundle the project for distribution
	@bash scripts/release.sh
