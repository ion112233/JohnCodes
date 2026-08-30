PY ?= python3
export PYTHONPATH := $(CURDIR)

.PHONY: help build build-all list preview clean

help:
	@echo "make build Q=content/questions/0001-two-sum.json   # render one Short"
	@echo "make build-all                                     # render every question"
	@echo "make preview Q=content/questions/0001-two-sum.json  # one still PNG (fast)"
	@echo "make list                                           # list questions"
	@echo "make clean                                          # wipe output/"

build:
	$(PY) -m johncodes build $(Q)

build-all:
	$(PY) -m johncodes build --all

list:
	$(PY) -m johncodes list

preview:
	$(PY) -m johncodes preview $(Q) --at $(or $(AT),0.6)

clean:
	rm -rf output
