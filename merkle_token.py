
import hashlib


##################
# Host Interface #
##################

_state_root = ''

def get_state_root():
  return _state_root

def set_state_root(new_state_root):
  global _state_root
  _state_root = new_state_root

def finish():
  print("Contract call ended manually, final state root is",_state_root)






#################
# contract code #
#################

# Some constants
num_address_bits=160
num_hash_bits=160
num_balance_bits=64
num_balance_bytes = (num_balance_bits+7)//8
num_address_bytes = (num_address_bits+7)//8
num_hash_bytes = (num_hash_bits+7)//8

num_transaction_bytes=105
num_transaction_bits=num_transaction_bytes*8

# some global variables
old_state_root = ''
transactions = []	# list of signed messages
balances = []		# list of balances
new_balances = []	# list of updated
address_chunks = []	# fragments of the address
proof_hashes = []	# list of merkle hashes
tree_encoding = []	# encoding of the tree structure
signatures = []		# list of signatures, each for a balance transfer
recovered_addresses = []# list of address

# hash function
def hash_(to_hash):
  h = hashlib.blake2b(digest_size=(num_hash_bits+7)//8)
  if type(to_hash)==int:
    to_hash = to_hash.to_bytes((to_hash.bit_length() + 7) // 8, 'big')
  h.update(to_hash)
  #print("hash_(",to_hash.hex(),") -> ",h.hexdigest())
  #print("hash_() ",to_hash.hex()," ->", h.hexdigest())
  return h.hexdigest()


# getters for address chunks, hash, balances, and address

addychunk_idx=0
def get_next_address_chunk():
  global addychunk_idx
  #print("get_next_address_chunk() addychunk_idx",addychunk_idx)
  addychunk = address_chunks[addychunk_idx]
  #print("get_next_address_chunk() addychunk_idx",addychunk_idx,"addychunk",addychunk)
  addychunk_idx+=1
  return addychunk
  
hash_idx=0
def get_next_hash():
  global hash_idx
  hash__ = proof_hashes[hash_idx]
  hash_idx+=1
  return hash__

old_balance_idx=0
def get_next_old_balance():
  global old_balance_idx
  balance = balances[old_balance_idx]
  old_balance_idx+=1
  return balance

new_balance_idx=0
def get_next_new_balance():
  global new_balance_idx
  balance = new_balances[new_balance_idx]
  new_balance_idx+=1
  return balance

address_idx=0
def get_next_address():
  global address_idx
  address = recovered_addresses[address_idx]
  address_idx+=1
  return address


# this recovers addresses by doing a single-pass through the tree encoding, consuming address chunks when needed
opcode_idx=0
def recover_addresses(address_prefix, depth):
  # if leaf, append address
  if depth == num_address_bits:
    recovered_addresses.append(address_prefix)
    return
  # otherwise, process tree node based on the opcode
  # "opcode" refers to a bit pair in the tree encoding
  global opcode_idx
  opcode = tree_encoding[opcode_idx]
  opcode_idx+=1
  if opcode == '11':
    recover_addresses(address_prefix+'0',depth+1)
    recover_addresses(address_prefix+'1',depth+1)
  elif opcode == '10':
    recover_addresses(address_prefix+'0', depth+1)
  elif opcode == '01':
    recover_addresses(address_prefix+'1', depth+1)
  elif opcode == '00':
    address_chunk = get_next_address_chunk()
    recover_addresses(address_prefix+address_chunk, depth+len(address_chunk))

# this is a single-pass to merkleize the old root and the new root
# this should be called after addresses are recovered, and new balances are created from transactions
def merklize_old_and_new_root(depth):
  print("merklize_old_and_new_root(",depth,")")
  # if leaf, hash it's address and value
  if depth == num_address_bits:
    print("merklize_old_and_new_root(",depth,")  leaf")
    old_balance = get_next_old_balance()
    new_balance = get_next_new_balance()
    address = get_next_address()
    return hash_(int(address+bin(old_balance)[2:].zfill(num_balance_bits),2)),\
           hash_(int(address+bin(new_balance)[2:].zfill(num_balance_bits),2))
  # otherwise, process the tree node, i.e. the opcode
  global opcode_idx
  opcode = tree_encoding[opcode_idx]
  print("merklize_old_and_new_root(",depth,")  opcode",opcode)
  opcode_idx+=1
  if opcode == '11':
    left_hash_old, left_hash_new = merklize_old_and_new_root(depth+1)
    right_hash_old, right_hash_new = merklize_old_and_new_root(depth+1)
    return hash_(int(left_hash_old+right_hash_old,16)), hash_(int(left_hash_new+right_hash_new,16))
  elif opcode == '10':
    left_hash_old, left_hash_new = merklize_old_and_new_root(depth+1)
    right_hash = get_next_hash()
    return hash_(int(left_hash_old+right_hash,16)),hash_(int(left_hash_new+right_hash,16))
  elif opcode == '01':
    right_hash_old, right_hash_new = merklize_old_and_new_root(depth+1)
    left_hash = get_next_hash()
    return hash_(int(left_hash+right_hash_old,16)),hash_(int(left_hash+right_hash_new,16))
  elif opcode == '00':
    address_chunk = get_next_address_chunk()
    print("merklize_old_and_new_root(",depth,")  opcode address_chunk",opcode,address_chunk)
    return merklize_old_and_new_root(depth+len(address_chunk))


# verify all signatures for token transfers
def verify_signature(sig):
  # TODO
  return True

def  verify_signatures():
  for sig in signatures:
    if not verify_signature(sig):
      finish()


# apply balance transfer from each transaction, creating a list of new balances
def execute_transactions():
  global new_balances
  new_balances = balances
  # TODO

# init calldata to global variables: transactions, balances, address chunks, proof hashes, tree encoding
def decode_calldata(calldata):
  # calldata is a dictionary for prot0typing, will later encode everything as a bytearray
  global transactions
  transactions = calldata["transactions"]
  global balances
  balances = calldata["balances"]
  global address_chunks
  address_chunks = calldata["address_chunks"]
  global proof_hashes
  proof_hashes = calldata["proof_hashes"]
  global tree_encoding
  tree_encoding = calldata["tree_encoding"]

# init indices before each tree traversal
def zero_global_indices():
  global opcode_idx
  global addychunk_idx
  global address_idx
  global new_balance_idx
  global old_balance_idx
  global hash_idx
  opcode_idx = 0
  address_index = 0
  new_balance_idx = 0
  old_balance_idx = 0
  addychunk_idx = 0
  hash_idx = 0


def main(calldata):
  # initialize global variables
  zero_global_indices()
  decode_calldata(calldata)
  # 1. Recover array of addresses
  recover_addresses('',0)
  # 2. verify all signatures
  verify_signatures()
  # 3. Build final balance array by executing all transactions, verifying no balance underflow.
  execute_transactions()
  # 4. Verify previous state root and compute new state root by traversing (b) (with (c), (d), (e), and balances computed in (2)).
  zero_global_indices()
  computed_hash_old,computed_hash_new = merklize_old_and_new_root(0)
  # 5. If previous state root is verified, then update state root
  old_state_root = get_state_root()
  if old_state_root == computed_hash_old:
    set_state_root(computed_hash_new)
  else:
    print("ERROR ERROR ERROR ERROR ERROR ERROR stored root != verified root:")
    print("stored root hash:", old_state_root)
    print("verified root hash:",computed_hash_old)
    print("computed new root hash",computed_hash_new)

