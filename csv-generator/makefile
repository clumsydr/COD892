.PHONY: all plot_all_qmdl scat_to_csv

SHELL := /bin/bash

DIR ?= ../data
OUT_DIR ?= ../qmdl_output
CSV_DIR ?= ../qmdl_output/
JOBS ?= 4

all: plot_all_qmdl

plot_all_qmdl:
	@if [ -z "$(DIR)" ]; then \
		echo "Error: Please specify DIR"; \
		exit 1; \
	fi
	@if [ -z "$(OUT_DIR)" ]; then \
		echo "Error: Please specify OUT_DIR"; \
		exit 1; \
	fi
	@echo "Searching for subdirectories containing .qmdl files in $(DIR)..."
	@subdirs=$$(find "$(DIR)" -mindepth 1 -type f -name "*.qmdl" -exec dirname {} \; 2>/dev/null | sort -u); \
	if [ -z "$$subdirs" ]; then \
		echo "No .qmdl files found in subdirectories of $(DIR)"; \
		exit 0; \
	fi; \
	for dir in $$subdirs; do \
		rel_dir=$$(realpath --relative-to="$(DIR)" "$$dir"); \
		out_subdir="$(OUT_DIR)/$$rel_dir"; \
		if [ -f "$$out_subdir/payloads.txt" ]; then \
			echo "Skipping $$dir: payloads.txt already exists"; \
			continue; \
		fi; \
		mkdir -p "$$out_subdir"; \
		echo ""; \
		echo "=================================================="; \
		echo "Processing .qmdl files in: $$dir"; \
		echo "Saving outputs to: $$out_subdir"; \
		echo "=================================================="; \
		mapfile -t qmdl_files < <(find "$$dir" -maxdepth 1 -type f -name "*.qmdl" | sort); \
		if [ "$${#qmdl_files[@]}" -gt 0 ]; then \
			echo "[1/3] Decoding $${#qmdl_files[@]} QMDL files using up to $(JOBS) parallel jobs..."; \
			tmpdir=$$(mktemp -d "$$out_subdir/.scat_tmp.XXXXXX"); \
			export tmpdir; \
			if ! printf '%s\0' "$${qmdl_files[@]}" | \
				xargs -0 -r -P "$(JOBS)" -I '{}' bash -c \
				'scat -t qc -d "$$1" > "$$tmpdir/$$(basename "$$1").txt"' _ '{}'; then \
				echo "ERROR: QMDL decoding failed in $$dir"; \
				rm -rf "$$tmpdir"; \
				exit 1; \
			fi; \
			: > "$$out_subdir/qmdl-to-scat.txt"; \
			for q_file in "$${qmdl_files[@]}"; do \
				cat "$$tmpdir/$$(basename "$$q_file").txt" >> "$$out_subdir/qmdl-to-scat.txt"; \
			done; \
			rm -rf "$$tmpdir"; \
			echo "[2/3] Extracting diagnostic payload bytes..."; \
			python3 qmdl-to-code.py "$$out_subdir/qmdl-to-scat.txt" "$$out_subdir/payloads.txt"; \
			echo "[3/3] Creating metrics CSV..."; \
			python3 dump_readable_logs.py "$$out_subdir/payloads.txt"; \
		fi; \
	done

scat_to_csv:
	@if [ -z "$(CSV_DIR)" ]; then \
		echo "Error: Please specify CSV_DIR"; \
		exit 1; \
	fi
	@echo "Searching for subdirectories containing qmdl-to-scat.txt in $(CSV_DIR)..."
	@subdirs=$$(find "$(CSV_DIR)" -mindepth 1 -type f -name "qmdl-to-scat.txt" -exec dirname {} \; 2>/dev/null | sort -u); \
	if [ -z "$$subdirs" ]; then \
		echo "No qmdl-to-scat.txt files found in $(CSV_DIR)"; \
		exit 0; \
	fi; \
	for out_subdir in $$subdirs; do \
		echo ""; \
		echo "=================================================="; \
		echo "Processing qmdl-to-scat.txt in: $$out_subdir"; \
		echo "=================================================="; \
		echo "[1/2] Extracting diagnostic payload bytes..."; \
		if ! python3 qmdl-to-code.py "$$out_subdir/qmdl-to-scat.txt" "$$out_subdir/payloads.txt"; then \
			echo "ERROR: Payload extraction failed in $$out_subdir"; \
			exit 1; \
		fi; \
		echo "[2/2] Creating metrics CSV..."; \
		if ! python3 dump_readable_logs.py "$$out_subdir/payloads.txt"; then \
			echo "ERROR: CSV creation failed in $$out_subdir"; \
			exit 1; \
		fi; \
	done
