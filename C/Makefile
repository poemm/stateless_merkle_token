#
#    Copyright 2019 Paul Dworzanski et al.
#
#    This file is part of c_ewasm_contracts.
#
#    c_ewasm_contracts is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    c_ewasm_contracts is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with c_ewasm_contracts.  If not, see <https://www.gnu.org/licenses/>.
#


# all of these exports can be passed as command-line arguments to make

# paths to tools
export LLVM := /home/user/repos/llvm9/llvm-project/build/bin/
#export LLVM := llvm-project/build/bin
#export LLVM := 
export WABT_DIR := ~/repos/wabt/wabt-1.0.10/
export BINARYEN_DIR := ~/repos/binaryen/binaryen-version_81/


export OPT := -O3

default: merkle_token



# dependencies checks and installation

wabt-install:
	git clone https://github.com/webassembly/wabt.git
	mkdir wabt/build
	cd wabt/build; cmake .. -DBUILD_TESTS=OFF
	cd wabt/build; make -j4
	touch wabt.READY

binaryen-install:
	git clone https://github.com/WebAssembly/binaryen.git
	cd binaryen; mkdir build
	cd binaryen/build; cmake ..
	cd binaryen/build; make -j4

llvm-install:
	# WARNING: should do this manually. Downloads a lot, requires a lot of system resources, and takes a long time. Might require restarting with `make` again if compilation has an error.
	git clone https://github.com/llvm/llvm-project.git
	cd llvm-project; mkdir build
	cd llvm-project/build; cmake -G 'Unix Makefiles' -DLLVM_ENABLE_PROJECTS="clang;libcxx;libcxxabi;lld" ../llvm
	cd llvm-project/build; make -j4

install: wabt-install binaryen-install
	#WARNING: this does not include llvm-install because this should be done manually

wabt-check:
ifeq (, $(shell which $(WABT_DIR)/wasm2wat))
	$(error "ERROR: Could not find wabt with wasm2wat, install it yourself and adjust path WABT_DIR in this makefile, or just install it with `make wabt-install`, and try again.")
endif

binaryen-check:
ifeq (, $(shell which $(BINARYEN_DIR)wasm-opt))
	$(error "ERROR: Could not find binaryen with wasm-dis, install it yourself and adjust path BINARYEN_DIR in this makefile, or just install it with `make binaryen-install`, and try again.")
endif

export LLVM_ERROR := "ERROR: Could not find llvm8+, install it yourself and adjust path LLVM_DIR in this makefile. It can also be found in some repositories. Install it yourself with `make llvm-install`, but this may fail and you should do it manually. WARNNG: 600MB+ download size, needs lots of RAM/disk to compile, compilation may fail the first try so need to restart multiple times.")

llvm-check:
ifeq (, $(shell which $(LLVM)clang))
	$(error $(LLVM_ERROR))
endif
ifeq (, $(shell which $(LLVM)opt))
	$(error $(LLVM_ERROR))
endif
ifeq (, $(shell which $(LLVM)lld))
	$(error $(LLVM_ERROR))
endif
ifeq (, $(shell which $(LLVM)wasm-ld))
	$(error $(LLVM_ERROR))
endif

test:
	cd ..; python3 merkle_token_offchain.py
	cp ../generated.yaml .
	~/repos/ethereum/scout_git_20190715/target/release/phase2-scout generated.yaml
	

native:
	gcc merkle_token.c -DNATIVE=1

# Build, convert, optimize
merkle_token:
	# build
	$(LLVM)clang -cc1 $(OPT) -emit-llvm -triple=wasm32-unknown-unknown-wasm merkle_token.c -o merkle_token.ll
	#$(LLVM)opt $(OPT) merkle_token.ll -o merkle_token.ll
	$(LLVM)llc $(OPT) -filetype=obj merkle_token.ll -o merkle_token.o
	$(LLVM)wasm-ld merkle_token.o -o merkle_token.wasm --no-entry -allow-undefined-file=eth2.syms -export=_main
	# done compiling, save text version
	$(WABT_DIR)wasm2wat merkle_token.wasm > merkle_token.wat
	# hack so that we export "main" instead of "_main"
	sed -i -e 's/(export "_main" (func $$_main))/(export "main" (func $$_main))/g' merkle_token.wat
	$(WABT_DIR)wat2wasm merkle_token.wat > merkle_token.wasm
	# size optimize
	$(BINARYEN_DIR)wasm-opt $(OPT) merkle_token.wasm -o merkle_token.wasm -g #-g keeps names but takes some size
	# save text format of final ewasm contract
	$(WABT_DIR)wasm2wat merkle_token.wasm > merkle_token2.wat
	# remove intermediate files
	rm -f merkle_token.ll merkle_token.o merkle_token_raw.wasm merkle_token_raw.wat


.PHONY: default all

