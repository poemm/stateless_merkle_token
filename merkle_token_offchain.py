



import merkle_token_contract

# flip this flag if you want more printed
verbose = 1




######################################################
# Off-chain tools for managing state, creating input #
######################################################

# the merkle tree is stored as a dictionary
#   keys are address prefix which correspond to nodes
#   values are the hash of that node (as a merkle tree), and the edge label (as a radix tree)
def build_merkle_tree(depth,sorted_addresses,accounts,merkle_tree):
  assert len(sorted_addresses)>0 # sorted_addresses is a nonempty list of addresses, also must be sorted
  assert (depth==0 and len(merkle_tree)==0) or depth>0 # merkle_tree is empty when this func is first called at depth 0
  # if leaf
  if len(sorted_addresses) == 1:
    addr = sorted_addresses[0]
    current_hash = merkle_token_contract.hash_(int(addr+bin(accounts[addr])[2:].zfill(merkle_token_contract.num_balance_bits),2))
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
    current_hash = merkle_token_contract.hash_(int(left_hash+right_hash,16))
    merkle_tree[address_prefix] = ( current_hash, address_chunk )
  return current_hash



# this function builds tree_encoding, address_chunks, and balances in depth-first pre-order, and builds proof_hashes in depth-first post-order
def build_merkle_proof(depth,sorted_addresses,accounts,merkle_tree,tree_encoding,address_chunks,balances,proof_hashes):
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



binary_calldata_encoding_flag = 1

def encode_calldata(transactions, balances, address_chunks, proof_hashes, tree_encoding, sorted_addresses=None):
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
   print("length of chunk: ",len(chunk))
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
    addy_as_bytes = int(addy,2).to_bytes((merkle_token_contract.num_address_bits + 7) // 8, 'big')
    addresses_bytes += addy_as_bytes
  encode_chunk(addresses_bytes)
  # encode balances
  balance_bytes = bytearray([])
  for b in balances:
    balance_bytes += b.to_bytes(8, byteorder='little')
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
  num_hash_bytes = merkle_token_contract.num_hash_bits//8
  for i in range(proof_hashes_length//num_hash_bytes):
    proof_hashes += [calldata[idx:idx+num_hash_bytes].hex()]
    idx+=num_hash_bytes
  print("proof hashes: ",proof_hashes)
  # decode sorted addresses, may be empty
  num_address_bytes = (merkle_token_contract.num_address_bits+7)//8
  addresses = []
  addresses_length=int.from_bytes(calldata[idx:idx+4],'little')
  idx+=4
  addresses_end = idx + addresses_length
  while idx < addresses_end:
    addresses += [bin(int.from_bytes(calldata[idx:idx+num_address_bytes],'big'))[2:].zfill(merkle_token_contract.num_address_bits)]
    idx += num_address_bytes
  print("addresses",addresses)
  # decode balances
  balances = []
  balances_length=int.from_bytes(calldata[idx:idx+4],'little')
  idx+=4
  num_balance_bytes = merkle_token_contract.num_balance_bits//8
  balance_bytes_end = idx + balances_length
  while idx < balance_bytes_end:
    balances += [int.from_bytes(calldata[idx:idx+num_balance_bytes],'little')]
    idx+=num_balance_bytes
  print("balances",balances)
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
  print("tree encoding ",tree_encoding)
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
  print("address chunks: ",address_chunks)
  #print( proof_hashes, balances, tree_encoding, address_chunks)
  return proof_hashes, balances, tree_encoding, address_chunks






#########
# Tests #
#########


def test_random(num_address_bits=16, num_addresses_in_witness=160):

  # init global in contract
  merkle_token_contract.num_address_bits = num_address_bits

  # generate random addresses and balances
  import random
  num_accounts=2**num_address_bits
  accounts = {bin(random.randint(0,2**num_address_bits-1))[2:].zfill(num_address_bits):random.randint(0, 2**merkle_token_contract.num_balance_bits-1) for i in range(num_accounts)}
  if verbose: print(accounts)

  # transactions are empty until we prototype them
  transactions = []

  # get addresses appearing in transactions, but for now just choose some randomly
  sorted_addresses = sorted(random.sample(accounts.keys(), num_addresses_in_witness))
  if verbose: print(sorted_addresses)

  # build merkle tree
  merkle_tree = {}
  build_merkle_tree(0, sorted(accounts), accounts, merkle_tree)
  if verbose: print()
  if verbose: print(merkle_tree)
  merkle_token_contract.set_state_root(merkle_tree[''][0])

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
  length_of_balances_bits = len(balances)*merkle_token_contract.num_balance_bits
  length_of_balances_bytes = (length_of_balances_bits + 7)//8
  length_of_hashes_bits = len(proof_hashes)*num_hash_bits
  length_of_hashes_bytes = (length_of_hashes_bits + 7)//8
  if verbose: print("sizes: tree_encoding:",length_of_tree_encoding_bytes,\
                  "  addy chunks",length_of_address_chunks_bytes,\
                  "  balances", length_of_balances_bytes,\
                  "  hashes", length_of_hashes_bytes,\
                  "  total", length_of_tree_encoding_bytes+length_of_address_chunks_bytes+length_of_balances_bytes+length_of_hashes_bytes)

  # encode calldata
  calldata = encode_calldata(transactions, balances, address_chunks,proof_hashes,tree_encoding)

  # call the contract
  merkle_token_contract.main(calldata)


def test_random_loop():

  for merkle_token_contract.num_address_bits in [10,12,14,16,18,20]:
    # generate random addresses and balances
    import random
    num_accounts=2**merkle_token_contract.num_address_bits
    accounts = {bin(random.randint(0,2**merkle_token_contract.num_address_bits-1))[2:].zfill(merkle_token_contract.num_address_bits):random.randint(0, 2**merkle_token_contract.num_balance_bits-1) for i in range(num_accounts)}
    # iterate over number of addresses in the witness
    for num_addresses_in_witness in [10,20,40,80,160]:
      print("\nnum accounts: 2^",merkle_token_contract.num_address_bits," num addresses in merkle proof:",num_addresses_in_witness)

      # transactions are empty until we prototype them
      transactions = []

      # sort addresses
      sorted_addresses = sorted(random.sample(accounts.keys(), num_addresses_in_witness))

      merkle_tree = {}
      build_merkle_tree(0, sorted(accounts), accounts, merkle_tree)
      merkle_token_contract.set_state_root(merkle_tree[''][0])

      tree_encoding = []
      address_chunks = []
      balances = []
      proof_hashes = []
      build_merkle_proof(0,sorted_addresses,accounts,merkle_tree,tree_encoding,address_chunks,balances,proof_hashes)

      length_of_tree_encoding_bits = len(tree_encoding)*2
      length_of_tree_encoding_bytes = (length_of_tree_encoding_bits+7)//8
      length_of_address_chunks_bits = len(address_chunks)*8+sum(len(chunk) for chunk in address_chunks)
      length_of_address_chunks_bytes = (length_of_address_chunks_bits + 7)//8
      length_of_balances_bits = len(balances)*merkle_token_contract.num_balance_bits
      length_of_balances_bytes = (length_of_balances_bits + 7)//8
      length_of_hashes_bits = len(proof_hashes)*merkle_token_contract.num_hash_bits
      length_of_hashes_bytes = (length_of_hashes_bits + 7)//8
      if verbose: print("  sizes: tree_encoding:",length_of_tree_encoding_bytes,\
                      "  addy chunks",length_of_address_chunks_bytes,\
                      "  balances", length_of_balances_bytes,\
                      "  hashes", length_of_hashes_bytes,\
                      "  total", length_of_tree_encoding_bytes+length_of_address_chunks_bytes+length_of_balances_bytes+length_of_hashes_bytes)

      # encode calldata
      calldata = encode_calldata(transactions, balances, address_chunks,proof_hashes,tree_encoding)

      # call the contract
      merkle_token_contract.main(calldata)



def test_handwritten(case):

  # choose a case below
  if case==1:
    merkle_token_contract.num_address_bits = 4
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
    merkle_token_contract.num_address_bits = 4
    accounts = {'1111': 30, '0011': 19, '1000': 23, '1011': 0, '1001': 18, '0001': 13, '0010': 25}
    transactions = [ ]
    sorted_addresses = ['0010', '0011', '1000', '1001', '1011', '1111']
  elif case==3:
    merkle_token_contract.num_address_bits = 4
    accounts = {'1001': 3, '1010': 11, '0111': 4, '1011': 8, '0101': 19, '1000': 21, '1111': 12, '0001': 20}
    transactions = [ ]
    sorted_addresses = ['0111', '1000', '1001', '1011', '1111']
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
  merkle_token_contract.set_state_root(merkle_tree[''][0])

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
  print("calldata has length",len(calldata),calldata)
  decode_calldata(calldata)
  
  # call the contract
  #merkle_token_contract.main(calldata)



if __name__ == "__main__":
  # uncomment one of these
  #test_random()
  #test_random_loop()
  test_handwritten(1)

