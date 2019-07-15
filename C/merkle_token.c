/*
    Copyright 2019 Paul Dworzanski et al.

    This file is part of c_ewasm_contracts.

    c_ewasm_contracts is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    c_ewasm_contracts is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with c_ewasm_contracts.  If not, see <https://www.gnu.org/licenses/>.
*/



/*

# to use, read the makefile to make sure you have dependencies, then:
make

# to test with scout:
path/to/scout/target/debug/phase2-scout test.yaml

*/

// stuff from stdint.h
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;
typedef char int8_t;
typedef short int16_t;
typedef int int32_t;
typedef long long int64_t;
typedef unsigned long size_t;



//#include "ewasm.h"
//#include "blake2.h"

///////////
// Types //
///////////

typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;

typedef char int8_t;
typedef short int16_t;
typedef int int32_t;
typedef long long int64_t;

typedef unsigned long size_t;

#define NULL 0  //TODO: check how libc defines NULL, I think this affects many things


//////////////////////////
// Types For Wasm Stuff //
//////////////////////////

typedef int32_t i32; // same as i32 in WebAssembly
typedef int64_t i64; // same as i64 in WebAssembly



//////////////////////////////
// Types for Ethereum Stuff //
//////////////////////////////

typedef uint8_t* bytes; // an array of bytes with unrestricted length
typedef uint8_t bytes32[32]; // an array of 32 bytes
typedef uint8_t address[20]; // an array of 20 bytes
typedef unsigned __int128 u128; // a 128 bit number, represented as a 16 bytes long little endian unsigned integer in memory, not sure if this works
//typedef uint256_t u256; // a 256 bit number, represented as a 32 bytes long little endian unsigned integer in memory, doesn't work
typedef uint32_t i32ptr; // same as i32 in WebAssembly, but treated as a pointer to a WebAssembly memory offset
// ethereum interface functions

////////////////////////////
// EEI Method Declaration //
////////////////////////////


void eth2_loadPreStateRoot(const uint32_t* offset);
uint32_t eth2_blockDataSize();
//void eth2_blockDataCopy(const uint32_t* outputOfset, uint32_t offset, uint32_t length);
void eth2_blockDataCopy(uint32_t offset, uint32_t length, uint32_t* outputOfset);
void eth2_savePostStateRoot(const uint32_t* offset);
//void eth2_pushNewDeposit(const uint32_t* offset, uint32_t length);
void eth2_pushNewDeposit(uint32_t* offset, uint32_t length);


////////////////////////////
// Memory Managment Stuff //
////////////////////////////

#define PAGE_SIZE 65536
#define GROWABLE_MEMORY true    // whether we want memory to be growable; true/false

extern unsigned char __heap_base;       // heap_base is immutable position where their model of heap grows down from, can ignore
extern unsigned char __data_end;        // data_end is immutable position in memory up to where statically allocated things are
extern unsigned long __builtin_wasm_memory_grow(int, unsigned long);    // first arg is mem idx 0, second arg is pages
extern unsigned long __builtin_wasm_memory_size(int);   // arg must be zero until more memory instances are available

/*
sample uses:
  unsigned char* heap_base = &__heap_base;
  unsigned char* data_end = &__data_end;
  unsigned int memory_size = __builtin_wasm_memory_size(0);
*/


__attribute__ ((noinline))
void* malloc(const size_t size){
  /*
    Our malloc is naive: we only append to the end of the previous allocation, starting at data_end. This is tuned for short runtimes where memory management cost is expensive, not many things are allocated, or not many things are freed.
    It seems (in May 2019) that LLVM->Wasm starts data_end at 1024 plus anything that is statically stored in memory at compile-time. So our heap starts at data_end and grows upwards.
    WARNING: There is a bug. LLVM may output code which uses a stack which grows down from `heap_base`. If this is the case, then heap and stack can collide. We are still evaluating our options, but for now, we leave this because it is memory efficient.
  */

  // this heap pointer starts at data_end and always increments upward
  static uint8_t* heap_ptr = &__data_end;

  uint32_t total_bytes_needed = (uint32_t)(heap_ptr)+size;
  // check whether we have enough memory, and handle if we don't
  if (total_bytes_needed > __builtin_wasm_memory_size(0)*PAGE_SIZE){ // if exceed current memory size
    #if GROWABLE_MEMORY==true
      uint32_t total_pages_needed = total_bytes_needed/PAGE_SIZE + (total_bytes_needed%PAGE_SIZE)?1:0;
      __builtin_wasm_memory_grow(0, total_pages_needed - __builtin_wasm_memory_size(0));
      // note: if we go over the limit of 2^32 bytes of memory, then this memory_grow will trap
    #else
      // for conciseness, we do nothing here, but if we access memory outside of bounds, then it will trap
    #endif
  }

  heap_ptr = (uint8_t*)total_bytes_needed;
  return (void*)(heap_ptr-size);

}








// these consts can't just be changed, since parts of the code assume they are unchanged
const int num_address_bits = 20;
const int num_hash_bits = 160;
const int num_balance_bits = 64;


uint64_t hash_input[] = {0,0,0,0,0,0,0,0};
uint64_t hash_output_old[] = {0,0,0,0,0};
uint64_t hash_output_new[] = {0,0,0,0,0};

uint8_t *proof_hashes;
uint8_t *addresses;
uint8_t *balances_old;
uint8_t *balances_new;
uint8_t *opcodes;
uint8_t *address_chunks;

/*
The hash inputs and outputs are on a stack, with old and new hashes side-by-side

  | old hash left | old hash right | new hash left | new hash right |

The hash output is put where the parent wants it.
*/
uint8_t *hash_output = 0;
uint64_t *hash_leaf_input[] = {0,0,0};


void merkleize_new_and_old_root(int depth, uint8_t *hash_stack_ptr, int leftFlag){
  uint8_t* old_hash_output_ptr = hash_stack_ptr - (leftFlag?80:60);
  uint8_t* new_hash_output_ptr = hash_stack_ptr - (leftFlag?40:20);
  if (depth == num_address_bits){
    // increment pointers to next address and next balances
    addresses += num_address_bits/8;
    balances_old += num_balance_bits/8;
    balances_new += num_balance_bits/8;
    // fill input with old data, then hash
    *(uint64_t*)hash_leaf_input = *(uint64_t*)addresses;
    *(uint64_t*)(hash_leaf_input+8) = *(uint64_t*)(addresses+8);
    *(uint32_t*)(hash_leaf_input+16) = *(uint32_t*)(addresses+16);
    *(uint64_t*)(hash_leaf_input+20) = *(uint64_t*)(balances_old);
    //blake2b( old_hash_output_ptr, num_hash_bits/8, hash_leaf_input, (num_address_bits+num_balance_bits)/8, NULL, 0 );
    // fill hashing input with new data, then hash
    *(uint64_t*)(hash_leaf_input+20) = *(uint64_t*)(balances_new);
    //blake2b( new_hash_output_ptr, num_hash_bits/8, hash_leaf_input, (num_address_bits+num_balance_bits)/8, NULL, 0 );
    return;
  }
  uint8_t opcode = *opcodes;
  opcodes++;
  int addy_chunk_bit_length;
  switch (opcode){
    case 0:
      // get address chunk
      addy_chunk_bit_length = (int) *address_chunks;
      // recurse with updated depth, same hash_stack_ptr and leftFlag
      merkleize_new_and_old_root(depth+addy_chunk_bit_length, hash_stack_ptr, leftFlag);
      break;
    case 1:
      // get hash from calldata, put in in both old and new left slots
      *(uint64_t*)hash_stack_ptr = *(uint64_t*)proof_hashes;
      *(uint64_t*)(hash_stack_ptr+8) = *(uint64_t*)(proof_hashes+8);
      *(uint32_t*)(hash_stack_ptr+16) = *(uint32_t*)(proof_hashes+16);
      *(uint64_t*)(hash_stack_ptr+40) = *(uint64_t*)proof_hashes;
      *(uint64_t*)(hash_stack_ptr+40+8) = *(uint64_t*)(proof_hashes+8);
      *(uint32_t*)(hash_stack_ptr+40+16) = *(uint32_t*)(proof_hashes+16);
      proof_hashes += 20;
      // recurse on right
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 0);
      // finally hash old and new
      //blake2b( old_hash_output_ptr, num_hash_bits/8, hash_stack_ptr, (num_hash_bits/8)*2, NULL, 0 );
      //blake2b( new_hash_output_ptr, num_hash_bits/8, hash_stack_ptr+40, (num_hash_bits/8)*2, NULL, 0 );
      break;
    case 2:
      // recurse on left
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 1);
      // get hash from calldata, put in in both old and new right slots
      *(uint64_t*)(hash_stack_ptr+20) = *(uint64_t*)proof_hashes;
      *(uint64_t*)(hash_stack_ptr+20+8) = *(uint64_t*)(proof_hashes+8);
      *(uint32_t*)(hash_stack_ptr+20+16) = *(uint32_t*)(proof_hashes+16);
      *(uint64_t*)(hash_stack_ptr+20+40) = *(uint64_t*)proof_hashes;
      *(uint64_t*)(hash_stack_ptr+20+40+8) = *(uint64_t*)(proof_hashes+8);
      *(uint32_t*)(hash_stack_ptr+20+40+16) = *(uint32_t*)(proof_hashes+16);
      proof_hashes += 20;
      // finally hash old and new
      //blake2b( old_hash_output_ptr, num_hash_bits/8, hash_stack_ptr, (num_hash_bits/8)*2, NULL, 0 );
      //blake2b( new_hash_output_ptr, num_hash_bits/8, hash_stack_ptr+40, (num_hash_bits/8)*2, NULL, 0 );
      break;
    case 3:
      // recurse both ways
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 1);
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 0);
      // hash what was returned
      //blake2b( old_hash_output_ptr, num_hash_bits/8, hash_stack_ptr, (num_hash_bits/8)*2, NULL, 0 );
      //blake2b( new_hash_output_ptr, num_hash_bits/8, hash_stack_ptr+40, (num_hash_bits/8)*2, NULL, 0 );
      break;
  }
}





uint8_t pre_state_root[] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
uint8_t post_state_root[] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};


void _main(void){

  // get calldata
  uint32_t calldata_size = eth2_blockDataSize();
  uint8_t* calldata = (uint8_t*) malloc( calldata_size );
  eth2_blockDataCopy( 0, calldata_size, (i32ptr*)calldata );

  // get old merkle root
  eth2_loadPreStateRoot((uint32_t*)pre_state_root);

  // parse calldata into pointers
  // proof hashes
  uint32_t proof_hashes_length = *(uint32_t*)calldata;
  proof_hashes = calldata+4;
  calldata += 4 + proof_hashes_length;
  // proof addresses
  uint32_t addresses_length = *(uint32_t*)calldata;
  addresses = calldata+4;
  calldata += 4 + proof_hashes_length;
  // balances
  uint32_t balances_length = *(uint32_t*)calldata;
  balances_old = calldata+4;
  calldata += 4 + proof_hashes_length;
  // opcodes
  uint32_t opcodes_length = *(uint32_t*)calldata;
  opcodes = calldata+4;
  calldata += 4 + opcodes_length;
  // address_chunks
  uint32_t address_chunks_length = *(uint32_t*)calldata;
  address_chunks = calldata+4;
  calldata += 4 + address_chunks_length;

  // verify transactions
  // TODO

  // apply transactions to get final balances
  balances_new = malloc(balances_length);
  // TODO

  // finally, merkleize prestate and poststate
  uint8_t* hash_stack_ptr = malloc(10000); // 10,000 is bigger than needed
  //merkleize_new_and_old_root(0, hash_stack_ptr+80, 1);

  // verify prestate against old merkle root hash
  for (int i=0; i<20; i++){
    if (hash_stack_ptr[i] != pre_state_root[i]){
      //return; // TODO error
    }
  }
  // update hash, hash_stack_ptr+40 should correspond to new merkle root hash
  for (int i=0; i<20; i++)
    post_state_root[i] = hash_stack_ptr[40+i];
  eth2_savePostStateRoot((uint32_t*)post_state_root);
}


