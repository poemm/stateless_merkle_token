



# import the token contract code, which has constants the hashing function
import merkle_token


# flip this flag if you want more printed
verbose = 0


##############################################
# Build Merkle Tree or Data for Merkle Proof #
##############################################

# the merkle tree is stored as a dictionary
#   keys are address prefix which correspond to nodes
#   values are the hash of that node (as a merkle tree), and the edge label (as a radix tree)
def build_merkle_tree(depth,sorted_addresses,accounts,merkle_tree):
  assert len(sorted_addresses)>0 # sorted_addresses is a nonempty list of addresses, also must be sorted
  assert (depth==0 and len(merkle_tree)==0) or depth>0 # merkle_tree is empty when this func is first called at depth 0
  # if leaf
  if len(sorted_addresses) == 1:
    addr = sorted_addresses[0]
    addr_as_bytes = int(addr,2).to_bytes(merkle_token.num_address_bytes, byteorder='big')
    balance_as_bits = bin(accounts[addr])[2:].zfill(merkle_token.num_balance_bits) #bin(int.from_bytes((accounts[addr]).to_bytes(merkle_token.num_balance_bytes, byteorder='little'), "big")[2:].zfill(merkle_token.num_balance_bits),2)
    balance_as_bytes = int(balance_as_bits,2).to_bytes(merkle_token.num_balance_bytes, byteorder='little')
    if verbose: print("going to hash addr balance",addr,accounts[addr],(addr_as_bytes+balance_as_bytes).hex())
    if verbose: print("num_address_bytes",merkle_token.num_address_bytes)
    current_hash = merkle_token.hash_(addr_as_bytes+balance_as_bytes)
    merkle_tree[addr[:depth]] = (current_hash, addr[depth:])
  else: # not leaf
    # find common address chunk for sorted addresses
    for d in range(depth,len(sorted_addresses[0])):
      if sorted_addresses[0][d] != sorted_addresses[-1][d]:
        break
    address_prefix = sorted_addresses[0][:depth]
    address_chunk = sorted_addresses[0][depth:d]
    # split sorted_addresses where they diverge
    for idx, address in enumerate(sorted_addresses):
      if address[d] != '0':
        break
    # recurse left and right
    left_hash = build_merkle_tree(d+1, sorted_addresses[:idx], accounts, merkle_tree)
    right_hash = build_merkle_tree(d+1, sorted_addresses[idx:], accounts, merkle_tree)
    hash_as_bytes = int(left_hash+right_hash,16).to_bytes(merkle_token.num_hash_bytes*2, byteorder='big')
    current_hash = merkle_token.hash_(hash_as_bytes)
    merkle_tree[address_prefix] = ( current_hash, address_chunk )
  return current_hash



# this function builds tree_encoding, address_chunks, and balances in depth-first pre-order, and builds proof_hashes in depth-first post-order
def build_merkle_proof(depth,sorted_addresses,accounts,merkle_tree,tree_encoding,address_chunks,balances,proof_hashes):
  #if verbose: print("build_merkle_proof(",depth,")")
  assert len(merkle_tree)>0 # the merkle tree exists, also built with build_merkle_tree() and contains the addresses in sorted_addresses
  assert len(sorted_addresses)>0 # sorted_addresses is a nonempty list of addresses, also must be sorted
  # get prefix of address at this depth
  address_prefix = sorted_addresses[0][:depth]
  # this function handles all proof hashes; traverses radix tree edges with labels longer than just '0' or '1'
  def handle_address_chunk(merkle_tree, address_prefix, address_chunk, tree_encoding, address_chunks):
    proof_hashes_for_chunk = []
    # before loop, process current chunk
    _, merkle_tree_chunk = merkle_tree[address_prefix]
    address_prefix+=merkle_tree_chunk
    if len(merkle_tree_chunk)>0:
      address_chunks += [merkle_tree_chunk]
      tree_encoding += ['00']
    # loop over address chunks
    idx = len(merkle_tree_chunk)
    endidx = len(address_chunk)
    while idx < endidx:
      if address_chunk[idx]=='0': # visit left child
        # get hash of right child
        merkle_tree_hash, _ = merkle_tree[address_prefix+'1']
        proof_hashes_for_chunk += [merkle_tree_hash]
        # get and process chunk, if any
        _, merkle_tree_chunk = merkle_tree[address_prefix+'0']
        # update merkle proof structures
        tree_encoding += ['10']
        if len(merkle_tree_chunk)>0:
          tree_encoding += ['00']
          address_chunks += [merkle_tree_chunk]
        # extend address prefix
        address_prefix += '0' + merkle_tree_chunk
      else: # visit right child
        # get hash of left child
        merkle_tree_hash, _ = merkle_tree[address_prefix+'0']
        proof_hashes_for_chunk += [merkle_tree_hash]
        # get and process chunk, if any
        _, merkle_tree_chunk = merkle_tree[address_prefix+'1']
        # update merkle proof structures
        tree_encoding += ['01']
        if len(merkle_tree_chunk)>0:
          tree_encoding += ['00']
          address_chunks += [merkle_tree_chunk]
        # extend address prefix
        address_prefix += '1' + merkle_tree_chunk
      idx += len(merkle_tree_chunk)+1
    return proof_hashes_for_chunk, address_prefix
  # two cases: leaf or addresses diverging in tree
  if len(sorted_addresses)==1: # leaf
    # handle the address_chunk, if any 
    address_chunk = sorted_addresses[0][depth:]
    proof_hashes_for_chunk,_ = handle_address_chunk(merkle_tree, address_prefix, address_chunk, tree_encoding, address_chunks)
    # update tree encoding for leaf, and append proof hashes after recursed
    balances += [accounts[sorted_addresses[0]]]
    proof_hashes += reversed(proof_hashes_for_chunk)
  else: # internal node with left and right children
    # handle the address_chunk, but first get the chunk, if any 
    for d in range(depth,len(sorted_addresses[0])):
      if sorted_addresses[0][d] != sorted_addresses[-1][d]:
        break
    address_chunk = sorted_addresses[0][depth:d]
    proof_hashes_for_chunk,address_prefix = handle_address_chunk(merkle_tree, address_prefix, address_chunk, tree_encoding, address_chunks)
    tree_encoding += ['11']
    # recurse, but first split sorted_addresses where they diverge
    for idx, address in enumerate(sorted_addresses):
      if address[d] != '0':
        break
    build_merkle_proof(depth+len(address_chunk)+1,sorted_addresses[:idx],accounts,merkle_tree,tree_encoding,address_chunks,balances,proof_hashes)
    build_merkle_proof(depth+len(address_chunk)+1,sorted_addresses[idx:],accounts,merkle_tree,tree_encoding,address_chunks,balances,proof_hashes)
    # update tree encoding
    proof_hashes += reversed(proof_hashes_for_chunk)




##########################
# Encode/Decode Calldata #
##########################

binary_calldata_encoding_flag = 1

def encode_calldata(transactions, balances, address_chunks, proof_hashes, tree_encoding, sorted_addresses=[]):
 if not binary_calldata_encoding_flag:
  # calldata is a dictionary for prototyping, will later encode everything as a bytearray
  calldata={}
  calldata["transactions"] = transactions
  calldata["balances"] = balances
  calldata["address_chunks"] = address_chunks
  calldata["proof_hashes"] = proof_hashes
  calldata["tree_encoding"] = tree_encoding
  return calldata
 else:
  # calldata as bytes
  calldata=bytearray([])
  # function to append chunk byte length before appending chunk
  def encode_chunk(chunk):
   #if verbose: print("length of chunk: ",len(chunk))
   if verbose: print("calldata appending chunk:",chunk.hex())
   nonlocal calldata
   calldata+=len(chunk).to_bytes(4, byteorder='little')
   calldata+=chunk
  # encode hashes as concatenation
  hashes_bytes = bytearray([])
  for h in proof_hashes:
    hashes_bytes += bytearray.fromhex(h)
  encode_chunk(hashes_bytes)
  # encode sorted addresses, may be empty
  addresses_bytes = bytearray([])
  for addy in sorted_addresses:
    addy_as_bytes = int(addy,2).to_bytes(merkle_token.num_address_bytes, 'big')
    addresses_bytes += addy_as_bytes
  encode_chunk(addresses_bytes)
  # encode balances
  balance_bytes = bytearray([])
  for b in balances:
    balance_bytes += b.to_bytes(merkle_token.num_balance_bytes, byteorder='little')
    if verbose: print("balance:",b.to_bytes(merkle_token.num_balance_bytes, byteorder='little').hex())
  if verbose: print("balance_bytes",balance_bytes.hex())
  encode_chunk(balance_bytes)
  # encode transactions
  # TODO
  # encode tree encoding
  tree_encoding_bytes = bytearray([])
  # NOTE this is the right way, but we don't feel like bit twiddling yet, so just give each opcode a byte
  #tree_encoding_length = len(tree_encoding)
  #tree_encoding_concat=''.join(tree_encoding)
  #tree_encoding_int = int(tree_encoding_concat, 2)
  #tree_encoding_bytes += tree_encoding_int.to_bytes((tree_encoding_int.bit_length()+7)//8, byteorder='little')
  # this is naive, but don't want to bit twiddle yet
  for e in tree_encoding:
    tree_encoding_bytes += bytearray([int(e, 2)])
  encode_chunk(tree_encoding_bytes)
  # encode address chunks
  address_chunks_bytes = bytearray([])
  for addy_chunk in address_chunks:
    addy_chunk_bits_length = len(addy_chunk)
    addy_chunk_encoding_int = int(addy_chunk, 2)
    address_chunks_bytes += bytearray([addy_chunk_bits_length]) + addy_chunk_encoding_int.to_bytes((addy_chunk_bits_length+7)//8, byteorder='big')
  encode_chunk(address_chunks_bytes)
  # done
  return calldata
  
  

def decode_calldata(calldata):
 if not binary_calldata_encoding_flag:
  pass
 else:
  idx = 0
  # decode proof hashes
  proof_hashes = []
  proof_hashes_length=int.from_bytes(calldata[idx:idx+4],'little')
  idx+=4
  for i in range(proof_hashes_length//merkle_token.num_hash_bytes):
    proof_hashes += [calldata[idx:idx+merkle_token.num_hash_bytes].hex()]
    idx+=merkle_token.num_hash_bytes
  if verbose: print("proof hashes: ",proof_hashes)
  # decode sorted addresses, may be empty
  addresses = []
  addresses_length=int.from_bytes(calldata[idx:idx+4],'little')
  idx+=4
  addresses_end = idx + addresses_length
  while idx < addresses_end:
    addresses += [bin(int.from_bytes(calldata[idx:idx+merkle_token.num_address_bytes],'big'))[2:].zfill(merkle_token.num_address_bits)]
    idx += merkle_token.num_address_bytes
  if verbose: print("addresses",addresses)
  # decode balances
  balances = []
  balances_length=int.from_bytes(calldata[idx:idx+4],'little')
  idx+=4
  balance_bytes_end = idx + balances_length
  while idx < balance_bytes_end:
    balances += [int.from_bytes(calldata[idx:idx+merkle_token.num_balance_bytes],'little')]
    idx+=merkle_token.num_balance_bytes
  if verbose: print("balances",balances)
  # decode transactions
  # TODO
  # decode tree encoding
  tree_encoding = []
  tree_encoding_length=int.from_bytes(calldata[idx:idx+4],'little')
  idx+=4
  tree_encoding_bytes_end = idx + tree_encoding_length
  while idx < tree_encoding_bytes_end:
    tree_encoding += [bin(int.from_bytes(calldata[idx:idx+1],'little'))[2:].zfill(2)]
    idx+=1
  if verbose: print("tree encoding ",tree_encoding)
  # decode address chunks or addresses
  address_chunks = []
  address_chunks_length=int.from_bytes(calldata[idx:idx+4],'little')
  idx+=4
  address_chunks_end = idx+address_chunks_length
  while idx < address_chunks_end:
    addy_chunk_bits_length = int.from_bytes(calldata[idx:idx+1],'little')
    idx += 1
    addy_chunk_bytes_length = (addy_chunk_bits_length+7)//8
    address_chunks += [bin(int.from_bytes(calldata[idx:idx+addy_chunk_bytes_length],'big'))[2:].zfill(addy_chunk_bits_length)]
    idx += addy_chunk_bytes_length
  #  idx += addy_chunk_bytes_length
  if verbose: print("address chunks: ",address_chunks)
  #if verbose: print( proof_hashes, balances, tree_encoding, address_chunks)
  return proof_hashes, balances, tree_encoding, address_chunks






##################
# Generate Tests #
##################

def generate_scout_test_yaml(num_address_bits=160, num_accounts_total=2**16, num_accounts_in_witness=20):
  merkle_tree, calldata = generate_random_test(num_address_bits, num_accounts_total, num_accounts_in_witness)
  merkle_root = merkle_tree[''][0]
  if verbose: print(calldata.hex())
  f = open('generated.yaml', 'w')
  file_text="""beacon_state:
  execution_scripts:
    - merkle_token.wasm
shard_pre_state:
  exec_env_states:
    - "%s000000000000000000000000"
shard_blocks:
  - env: 0
    data: ""
  - env: 0
    data: "%s"
shard_post_state:
  exec_env_states:
    - "%s000000000000000000000000"
"""%(merkle_root,calldata.hex(),merkle_root)
  if verbose: print(file_text)
  f.write(file_text)
  f.close


# this is useful when pasting tests into C, outputs list like: [5, 240, ..., 143]
def convert_calldata_to_list_of_uint8(calldata):
  return [int(calldata[i:i+2],16) for i in range(0, len(calldata), 2)]


# This generates a random witness.
def generate_random_test(num_address_bits=160, num_accounts_total=2**16, num_accounts_in_witness=20):

  # init global in contract
  merkle_token.num_address_bits = num_address_bits
  merkle_token.num_address_bytes = (num_address_bits+7)//8

  # generate random addresses and balances
  import random
  accounts = {bin(random.randint(0,2**merkle_token.num_address_bits-1))[2:].zfill(merkle_token.num_address_bits):random.randint(0, 2**merkle_token.num_balance_bits-1) for i in range(num_accounts_total)}
  if verbose: print(accounts)

  # transactions are empty until we prototype them
  transactions = []

  # get addresses appearing in transactions, but for now just choose some randomly
  sorted_addresses = sorted(random.sample(accounts.keys(), num_accounts_in_witness))
  if verbose: print(sorted_addresses)

  # build merkle tree
  merkle_tree = {}
  build_merkle_tree(0, sorted(accounts), accounts, merkle_tree)
  if verbose: print()
  if verbose: print(merkle_tree)
  merkle_token.set_state_root(merkle_tree[''][0])

  # build merkle proof for sorted_accounts
  tree_encoding = []
  address_chunks = []
  balances = []
  proof_hashes = []
  build_merkle_proof(0,sorted_addresses,accounts,merkle_tree,tree_encoding,address_chunks,balances,proof_hashes)
  if verbose: print()
  if verbose: print("tree_encoding: ", tree_encoding)
  if verbose: print("address_chunks ", address_chunks)
  if verbose: print("balances ", balances)
  if verbose: print("proof_hashes ", proof_hashes)

  # print witness length info
  length_of_tree_encoding_bits = len(tree_encoding)*2
  length_of_tree_encoding_bytes = (length_of_tree_encoding_bits+7)//8
  length_of_address_chunks_bits = len(address_chunks)*8+sum(len(chunk) for chunk in address_chunks)
  length_of_address_chunks_bytes = (length_of_address_chunks_bits + 7)//8
  length_of_balances_bits = len(balances)*merkle_token.num_balance_bits
  length_of_balances_bytes = (length_of_balances_bits + 7)//8
  length_of_hashes_bits = len(proof_hashes)*merkle_token.num_hash_bits
  length_of_hashes_bytes = (length_of_hashes_bits + 7)//8
  if verbose: print("sizes: tree_encoding:",length_of_tree_encoding_bytes,\
                  "  addy chunks",length_of_address_chunks_bytes,\
                  "  balances", length_of_balances_bytes,\
                  "  hashes", length_of_hashes_bytes,\
                  "  total", length_of_tree_encoding_bytes+length_of_address_chunks_bytes+length_of_balances_bytes+length_of_hashes_bytes)

  # encode calldata
  calldata = encode_calldata(transactions, balances, address_chunks,proof_hashes,tree_encoding,sorted_addresses=sorted_addresses)
  #if verbose: print("calldata has length",len(calldata),calldata.hex())
  #if verbose: print("merkle_root",merkle_tree[''][0])

  # call the contract written in Python
  #merkle_token.main(calldata)

  return merkle_tree, calldata




#####################
# Handwritten Tests #
#####################

# I have these test trees and witnesses drawn on paper, used for troubleshooting
def test_handwritten(case):

  # choose a case below
  if case==1:
    merkle_token.num_address_bits = 4
    merkle_token.num_address_bytes = (merkle_token.num_address_bits+7)//8
    # all accounts and their balances
    accounts = { \
      '0010': 2, \
      '0011': 3, \
      '0110': 4, \
      '1010': 5, \
      '1110': 6, \
      '1111': 7, \
    }
    """ resulting merkle-tree will look like:
    '': ('001020011301104101051110611117', '')
     '0': ('001020011301104', '')
      '00': ('0010200113', '1')
       '0010': ('00102', '')
       '0011': ('00113', '')
      '01': ('01104', '10')
     '1': ('101051110611117', '')
      '10': ('10105', '10')
      '11': ('1110611117', '1')
       '1110': ('11106', '')
       '1111': ('11117', '')
    """
    # transactions: list of (from,to,amount)
    transactions = [ ]
    sorted_addresses = ['0010','1010','1111']
  elif case==2:
    merkle_token.num_address_bits = 4
    merkle_token.num_address_bytes = (merkle_token.num_address_bits+7)//8
    accounts = {'1111': 30, '0011': 19, '1000': 23, '1011': 0, '1001': 18, '0001': 13, '0010': 25}
    transactions = [ ]
    sorted_addresses = ['0010', '0011', '1000', '1001', '1011', '1111']
  elif case==3:
    merkle_token.num_address_bits = 4
    merkle_token.num_address_bytes = (merkle_token.num_address_bits+7)//8
    accounts = {'1001': 3, '1010': 11, '0111': 4, '1011': 8, '0101': 19, '1000': 21, '1111': 12, '0001': 20}
    transactions = [ ]
    sorted_addresses = ['0111', '1000', '1001', '1011', '1111']
  elif case==4:
    merkle_token.num_address_bits = 4
    merkle_token.num_address_bytes = (merkle_token.num_address_bits+7)//8
    accounts = {'1000': 15680198381451287781, '0101': 15153962711451731809, '0010': 2045214529773071571, '1010': 2440942951611918511, '0111': 13184077568327963006}
    transactions = [ ]
    sorted_addresses = ['0010', '0111', '1000', '1010']
  elif case==5:
    merkle_token.num_address_bits = 4
    merkle_token.num_address_bytes = (merkle_token.num_address_bits+7)//8
    accounts={'1011': 8938256444143492206, '0111': 7815384352756830268, '0010': 9730086830208173111, '1101': 900156042085247510, '0100': 2736464869549539395, '0000': 10124408162674135124, '1111': 17564933267269664189}
    transactions = [ ]
    sorted_addresses = ['0000', '0100', '0111', '1101']
  elif case==6:
    merkle_token.num_address_bits = 4
    merkle_token.num_address_bytes = (merkle_token.num_address_bits+7)//8
    accounts={'0011': 1717550796369595821, '1010': 2179697818989203640, '1011': 16448714579139372091, '0101': 5707742151784323691, '1111': 2000623183052550128, '0110': 7490042243900540407, '0001': 12339517053306537546}
    transactions = [ ]
    sorted_addresses = ['0001', '0011', '0101', '0110']
  elif case==7:
    merkle_token.num_address_bits = 5
    merkle_token.num_address_bytes = (merkle_token.num_address_bits+7)//8
    accounts={'00011': 17119406195254483079, '11010': 3899075762303900198, '10011': 9486444053537439199, '00111': 5440628254627292198, '10100': 14895533570285341770, '10001': 3019732735682843023}
    transactions = [ ]
    sorted_addresses = ['00111', '10011', '10100', '11010']
  else:
    return


  # print all of the accounts, and the address to be used in the proof
  print("accounts:",accounts)
  print("sorted_accounts (appearing in transactions):",sorted_addresses)

  # build merkle tree
  merkle_tree = {}
  build_merkle_tree(0, sorted(accounts), accounts, merkle_tree)
  # print the merkle tree, it is a dictionary
  print()
  print("merkle_tree:")
  #print("merkle_tree:",merkle_tree)
  for x in merkle_tree:
    print (x,merkle_tree[x])

  # init previous state root to be used by contract
  merkle_token.set_state_root(merkle_tree[''][0])

  # build the merkle proof
  tree_encoding = []
  address_chunks = []
  balances = []
  proof_hashes = []
  print()
  build_merkle_proof(0,sorted_addresses,accounts,merkle_tree,tree_encoding,address_chunks,balances,proof_hashes)
  print()
  print("tree_encoding: ", tree_encoding)
  print("address_chunks ", address_chunks)
  print("balances ", balances)
  print("proof_hashes ", proof_hashes)

  # encode calldata
  calldata = encode_calldata(transactions, balances, address_chunks,proof_hashes,tree_encoding, sorted_addresses=sorted_addresses)
  print("calldata has length",len(calldata),calldata.hex())
  decode_calldata(calldata)
  
  # call the contract written in python
  #merkle_token.main(calldata)






if __name__ == "__main__":
  # uncomment one of these
  #generate_random_test_naive()
  generate_scout_test_yaml()
  #test_handwritten(7)
