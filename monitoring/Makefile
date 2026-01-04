DURATION ?= 60s
INTERVAL ?= 1
OUTPUT_FILE ?= resources.csv
FILE ?= resources.csv

.PHONY: install record clean help analyze

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Check for vmstat and python dependencies
	@echo "Checking for vmstat..."
	@if command -v vmstat >/dev/null 2>&1; then \
		echo "vmstat is installed."; \
	else \
		echo "Error: vmstat not found. Please install procps package."; \
		exit 1; \
	fi
	@echo "Checking for analysis dependencies (pandas, matplotlib)..."
	@if ! python3 -c "import pandas, matplotlib" >/dev/null 2>&1; then \
		echo "Warning: Python libraries (pandas, matplotlib) missing. 'make analyze' will fail."; \
		echo "Install with: pip install pandas matplotlib"; \
	else \
		echo "Analysis dependencies found."; \
	fi

record: ## Record resources. Usage: make record DURATION=30s INTERVAL=1 OUTPUT_FILE=res.csv
	@./monitor_resources.sh --duration $(DURATION) --interval $(INTERVAL) --output $(OUTPUT_FILE)

analyze: ## Generate charts from data. Usage: make analyze FILE=res.csv
	@python3 analyze_resources.py --input $(FILE)

clean: ## Remove generated CSV and PNG files
	rm -f *.csv *.png
