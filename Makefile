.PHONY: lint test check
lint:
	yamllint . && ansible-lint
test:
	pytest -v
check: lint test
	ansible-playbook --syntax-check site.yml migration.yml doctor.yml
