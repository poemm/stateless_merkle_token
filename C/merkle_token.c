
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

# to compile, read top of Makefile to make sure you have dependencies, then:
make

# to test with scout:
path/to/scout/target/release/phase2-scout test.yaml

*/

#include "ewasm.h"
#include "blake2.h"


// these consts can't just be changed, since parts of the code assume they are unchanged
#define num_address_bits 160
#define num_hash_bits 160
#define num_balance_bits 64

#define num_address_bytes (num_address_bits+7)/8
#define num_hash_bytes (num_hash_bits+7)/8
#define num_balance_bytes (num_balance_bits+7)/8


// pointers related to merkle proofs, init to 0 otherwise linker has errors
uint8_t *proof_hashes = 0;
uint8_t *addresses = 0;
uint8_t *balances_old = 0;
uint8_t *balances_new = 0;
uint8_t *opcodes = 0;
uint8_t *address_chunks = 0;

// this is input to blake2b to hash the leaf, declare here for convenience
uint64_t leaf_buffer[] = {0,0,0,0,0,0};
uint64_t *leaf_buffer_balance = (uint64_t*)(((uint8_t*)leaf_buffer)+num_address_bytes);


/*
This function does all of the merklization, in a single-pass, of both old and new root.

depth is the depth of the tree node corresponding to this recursive function call.

hash_stack_ptr is the stack which maintains hash inputs and outputs.
The stack grows with each recursive call of this function, and shrinks with each return.
A stack item looks like this, where "old hash left" means the pre-state hash of the left child:
byte offset:  0               20               40              60               80
data:         | old hash left | old hash right | new hash left | new hash right |
The hash output is put in indices to the left of this stack item, i.e. in its parent's stack item.

leftFlag is 1 if this function is called on the left child, and 0 if right.
*/
void merkleize_new_and_old_root(int depth, uint8_t *hash_stack_ptr, int leftFlag){
  // compute the offset to put the resulting hash for this node
  uint8_t* old_hash_output_ptr = hash_stack_ptr - (leftFlag?80:60);
  uint8_t* new_hash_output_ptr = hash_stack_ptr - (leftFlag?40:20);
  // if we are at a leaf, then hash it and return
  if (depth == num_address_bits){
    // fill buffer with address
    memcpy(leaf_buffer,addresses,num_address_bytes);
    //memcpy(leaf_buffer+num_address_bytes,balances_old,num_balance_bytes);
    memcpy(leaf_buffer_balance,balances_old,num_balance_bytes);
    blake2b( old_hash_output_ptr, num_hash_bytes, leaf_buffer, num_address_bytes+num_balance_bytes, NULL, 0 );
    // fill buffer with new value, then hash
    memcpy(leaf_buffer_balance,balances_new,num_balance_bytes);
    blake2b( new_hash_output_ptr, num_hash_bytes, leaf_buffer, num_address_bytes+num_balance_bytes, NULL, 0 );
    // increment pointers to next address and next balances
    addresses += num_address_bytes;
    balances_old += num_balance_bits/8;
    balances_new += num_balance_bits/8;
    return;
  }
  uint8_t opcode = *opcodes;
  opcodes++;
  uint8_t addy_chunk_bit_length, addy_chunk_byte_length;
  switch (opcode){
    case 0b00:
      // get address chunk
      addy_chunk_bit_length = *address_chunks;
      addy_chunk_byte_length = (addy_chunk_bit_length+7)/8;
      address_chunks += 1 + addy_chunk_byte_length;
      // recurse with updated depth, same hash_stack_ptr and leftFlag
      merkleize_new_and_old_root(depth+addy_chunk_bit_length, hash_stack_ptr, leftFlag);
      break;
    case 0b01:
      // recurse on right
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 0);
      // get hash from calldata, put in in both old and new left slots
      memcpy(hash_stack_ptr,proof_hashes,num_hash_bytes);
      memcpy(hash_stack_ptr+40,proof_hashes,num_hash_bytes);
      proof_hashes += num_hash_bytes;
      // finally hash old and new
      blake2b( old_hash_output_ptr, num_hash_bytes, hash_stack_ptr, num_hash_bytes*2, NULL, 0 );
      blake2b( new_hash_output_ptr, num_hash_bytes, hash_stack_ptr+40, num_hash_bytes*2, NULL, 0 );
      break;
    case 0b10:
      // recurse on left
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 1);
      // get hash from calldata, put in in both old and new right slots
      memcpy(hash_stack_ptr+20,proof_hashes,num_hash_bytes);
      memcpy(hash_stack_ptr+20+40,proof_hashes,num_hash_bytes);
      proof_hashes += num_hash_bytes;
      // finally hash old and new
      blake2b( old_hash_output_ptr, num_hash_bytes, hash_stack_ptr, num_hash_bytes*2, NULL, 0 );
      blake2b( new_hash_output_ptr, num_hash_bytes, hash_stack_ptr+40, num_hash_bytes*2, NULL, 0 );
      break;
    case 0b11:
      // recurse both left and right
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 1);
      merkleize_new_and_old_root(depth+1, hash_stack_ptr+80, 0);
      // hash what was returned
      blake2b( old_hash_output_ptr, num_hash_bytes, hash_stack_ptr, num_hash_bytes*2, NULL, 0 );
      blake2b( new_hash_output_ptr, num_hash_bytes, hash_stack_ptr+40, num_hash_bytes*2, NULL, 0 );
      break;
  }
}


// merkle roots, 32 bytes each
uint8_t post_state_root[] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
uint8_t pre_state_root[] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};


void _main(void){

  // get calldata
  uint32_t calldata_size = eth2_blockDataSize();
  if (calldata_size == 0)
    return; // error, revert
  uint8_t* calldata = (uint8_t*) malloc( calldata_size );
  eth2_blockDataCopy( (i32ptr*)calldata, 0, calldata_size  );

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
  calldata += 4 + addresses_length;
  // balances
  uint32_t balances_length = *(uint32_t*)calldata;
  balances_old = calldata+4;
  calldata += 4 + balances_length;
  // opcodes
  uint32_t opcodes_length = *(uint32_t*)calldata;
  opcodes = calldata+4;
  calldata += 4 + opcodes_length;
  // address_chunks
  uint32_t address_chunks_length = *(uint32_t*)calldata;
  address_chunks = calldata+4;
  calldata += 4 + address_chunks_length;

  // verify transactions
  // TODO: verify signatures here

  // apply balance transfers from transactions
  balances_new = malloc(balances_length);
  memcpy(balances_new, balances_old, balances_length);
  // TODO: apply balance transfers here, new balances are currently a copy of old ones

  // finally, merkleize prestate and poststate
  uint8_t* hash_stack_ptr = malloc(10000); // 10,000 bytes is bigger than needed for depth 50 tree
  merkleize_new_and_old_root(0, hash_stack_ptr+80, 1);

  // update hash, hash_stack_ptr+40 should correspond to new merkle root hash
  for (int i=0; i<20; i++)
    post_state_root[i] = hash_stack_ptr[40+i];

  // verify prestate against old merkle root hash
  for (int i=0; i<20; i++){
    if (hash_stack_ptr[i] != pre_state_root[i]){
    //  return; // error, revert
    }
  }

}

