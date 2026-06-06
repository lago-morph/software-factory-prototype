# Run every backbone component's self-test (stdlib-only; no pip, offline).
#   make -C factory test
.PHONY: test
test:
	@set -e; \
	for d in c*/; do \
	  echo "=== $$d ==="; \
	  ( cd "$$d" && bash test.sh ); \
	done; \
	echo "ALL COMPONENT TESTS PASSED"
