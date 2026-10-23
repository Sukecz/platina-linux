.PHONY: help check test doctor prepare sync kernel images verify audit version splash
PROFILE ?= candidate
OUTPUT ?= candidate-$(shell date +%Y%m%d-%H%M%S)
help:
	@./scripts/project --help
check:
	@./scripts/project check
	@python3 scripts/check-public-tree.py
test:
	@python3 -m unittest discover -s tests -v
doctor:
	@./scripts/project doctor
prepare:
	@./scripts/project prepare --profile "$(PROFILE)"
sync:
	@./scripts/project sync --profile "$(PROFILE)"
kernel:
	@./scripts/project kernel --profile "$(PROFILE)"
images:
	@./scripts/project images --output "$(OUTPUT)"
verify:
	@./scripts/project verify "$(DIR)"
audit:
	@./scripts/project audit "$(DIR)"
version:
	@./scripts/platina-release.py show
splash:
	@./scripts/platina-release.py build
