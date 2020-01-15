
MOVED WORK TO https://github.com/poemm/stateless_kmm_token. THIS REPO HAS OLD INCOMPLETE VERSION.

# Stateless Token Contract

## The Code

`merkle_token.py` is the on-chain contract logic, to be ported and compiled to Wasm. `merkle_token_tools.py` is for off-chain things like generating merkle proofs, although algorithms are naive for now. To generate a Scout yaml test case, including a merkle proof encoded in the way described below, try:

```
python3 merkle_token_tools.py
# should output: generated.yaml
```

## Introduction

This is an experiment to write a stateless token contract for blockchains like Ethereum. A problem with current token contracts is that the state (account addresses and balances) is stored on-chain, and on-chain state growth is said to be unsustainable. A proposed solution is stateless contracts, which only put a state hash on-chain, and all account balances are maintained off-chain.

A stateless token contract must (i) verify account balances against the on-chain state hash, (ii) apply balance transfers, and (iii) update the state hash to finalize balance transfers. In this document and code, we use a [Merkle hash](https://en.wikipedia.org/wiki/Merkle_tree) as the state hash, and maintain all accounts and balances off-chain in a binary tree. One of our innovations is that the Merkle proofs are encoded in a way which is convenient to Merkleize on-chain.

Related work includes Vitalik Buterin et. al.'s [SSZ partials as Merkle proofs](https://github.com/ethereum/eth2.0-specs/pull/1186/) and Alexey Akhunov's [Merkle proofs for Eth 1.0](https://github.com/ledgerwatch/turbo-geth/blob/visual/docs/programmers_guide/guide.md). An alternative to Merkle trees is RSA accumulators. Another alternative is using zero-knowledge tricks to encode and verify token transfers more succinctly, in both space and time.



## Binary Tree

**Definition.** [Knuth, 1997, pg 312]
A *binary tree* is a finite set of nodes that either is empty, or consists of a root and the elements of two disjoint binary trees called the left and right subtrees of the root.

**Definitions.**
The *root node* of tree is the distinguished node which was not part of a subtree.

A *leaf node* of a binary tree has empty left and right subtrees.

An *internal node* is any node other than leaf nodes.

An *edge*, drawn as a line segment between a node and its subtree, represents a node to its subtree relationship.

A *child node* of a node, is the root of a subtree of that node.


**Example.** We enumerate all binary trees up to three nodes. By convention, the root node is at the top and the leaves are at the bottom.
```
zero nodes:
(empty tree)

One node:
   x

Two nodes:
    x  x
   /    \
  x      x

Three nodes:
   x        x      x   x     x
  / \      /      /     \     \
 x   x    x      x       x     x
         /       \      /       \
        x         x    x         x
```



## Edge Labels: Prefix Tree ("Trie"), Radix Tree, Paths

**Definition.** A tree with *edge labels* has a label on each edge, where each label is an element from any set (e.g. a binary string from a set of binary strings).

**Definition.** A *prefix tree* ("trie") is a tree with edge labels, and each node has a unique label to each of its children.

**Definition** A *binary path* to a node of a binary tree: Consider a prefix binary tree with label `0` on each edge to a left child and `1` on each edge to a right child. Traverse from root to the node, append `0` if visit left child and `1` if visit right child, finish with a sequence of `0`'s and `1`'s.

**Example.** A prefix tree with label `0` on left edges and `1` on right edges. Leaves have paths: `01`, `1100`, `1101`
```
     x
   0/  \1
   x    x
    \1   \1
     x    x
        0/
        x
      0/  \1
      x    x
```

**Definition.** A *radix tree* is a prefix tree with minumum number of nodes -- each node which is an only child is removed and it's edge label is concatenating with the edge above.

**Example.** The same tree as a radix tree.
```
      x
   01/ \110
    x   x
      0/ \1
      x   x
```



## Node Labels: Children Pattern Sequence

**Definition** A tree with *node labels* has a label at each node.

**Definition.** [Katajainen and Makinen, 1990]
A *children pattern sequence* is as follows: Label each node of binary tree `00` for leaf, `01` if it only has a right child, `10` if it only has a left child, and `11` if it has two children. Traverse in [depth-first pre-order](https://en.wikipedia.org/wiki/Tree_traversal#Pre-order_(NLR)) collecting the sequence of labels.

**Example.** Consider leaves with paths: `01`, `1100`, `1101`
```
     11
    /  \
   01  01
    \    \
    00   10
         /
        11
       /  \
      00   00
Children Pattern Sequence: 11 01 00 01 10 11 00 00
```

**Example.** Corresponding radix tree with edge label `0` for left child and `1` for right child:
```
     11
   01/ \110
    00  11
      0/ \1
      00  00
Children Pattern Sequence: 11 00 11 00 00
Edge Label sequence (also depth-first pre-order): 01 110 0 1
```

**Remark.** In the example, note that the first image, the tree can be recovered with the Children Pattern Sequence. In the radix form, the tree can be recovered with the Children Pattern Sequence along with the Edge Label Sequence, which can also be used to recover the original (non-radix) tree.


## Fixed Depth Tree

**Definition.**
The *depth* of the node in a tree is the number of edges between it and the root.
A *fixed depth tree* has all leaves at the same depth.

**Example.** Consider fixed depth binary tree of depth 3, and paths to leaves: `010`, `110`, `111`.
```
     x
    /  \
   x    x
    \    \
    x     x 
   /     / \
  x     x  x 

Corresponding radix tree using label 0 for left child and 1 for right child:
     x 
 010/  \11
   x    x 
      0/ \1
      x   x
```

**Definition.** We define *Optimization 1* and *Optimizaiton 2* below by example.

**Example.** Consider the tree in the above example.
```
Optimization 1: leaves need no labels, since depth is fixed, so can determine whether it is a leaf from its depth.
     11
 010/  \11
        11
      0/ \1
Optimization 1 Node Label sequence: 11 11
Optimization 1 Edge Label sequence: 010 110 0 1


Optimization 2: Edge labels 0 and 1 are redundant because they can be determined from the child pattern sequence. Because we no longer use label 00 from Optimization 1, we add a new node with label 00 for each edge with label longer than length 1, drop the first bit from its label, and put the rest of the label on the child of the new node labeled 00.
      11
    /   \
   00   00
    \10  \1
         11
         / \
Optimization 2: Node Label Sequence: 11 00 00 11
Optimization 2: Edge Label Sequence: 10 1
```


## Fixed-Depth Binary Tree To Represent Token Accounts

**Remark.** Notice that for a fixed-depth binary tree, the path to each leaf corresponds to a unique fixed-length binary sequence. So each leaf can correspond to a token address, since an address is a fixed-length binary sequence. The balance can also be stored at the leaf, and all accounts can be represented a as such a binary tree.


## Binary Encoding of Merkle Proof

**Definition.** The *Merkle proof* ia a binary encoding as a concatenation of the following:

```
number of bytes of hashes as a 4 byte little-endian integer
concatenation of all raw proof hashe bytes, in depth-first post-order of a traversal of the witness

number of bytes for all balances as a 4 byte little-endian integer
concatenation of leaf balances in depth-first pre-order of a traversal of the witness

number of bytes for all transactions as a 4 byte little-endian integer
concatenation of raw transaction bytes, each prefixed with a byte for the signer's index in the sorted list of addresses in this merkle proof

number of bytes for the node label sequence in optimization 2 as a 4 byte little-endian integer
the tree structure in optimization 2 (for now, it is one byte per node with least significant bits as 00, 01, 10, or 11, but later will just concatenate the bits)

number of bytes for the edge label sequence from optimization 2 as a 4 byte little-endian integer
the edge label sequence, with each value prefixed with a new byte giving its length.
```

**Remark.** This encoding has some inefficiencies. We hope to approach the theoretical optimum in size.


## Address(es) Recovery.

**Remark.** Addresses need not be provided in the binary encoding because they can be recovered from the rest of the Merkle proof.

**Algorithm.** Recover addresses from a tree with Optimization 2.
```
Input: Edge and Node label sequences for a tree with Optimization 2.
Output: List of addresses, in lexographical order.
RECOVER_ADDRESSES(current prefix, edge label sequence, node label seqence )
If length of current prefix is full address, append it to the list of addresses and return.
Otherwise:
  Get next value from node label seqence
  if 11: Recurse with 0 appended to current_prefix.
         Recurse with 1 appended to current_prefix.
  if 01: Recurse with 0 appended to current_prefix.
  if 10: Recurse with 1 appended to current_prefix.
  if 00: Recurse with next edge label appended to current_prefix.
  Remove any labels added in this function call, then return.
```




## Merkleizing

**Definition.** We define *balance sequence*, *merkle proof*, and *merkle hash sequence* by example below.

**Example.** Consider the example with Optimization 2. Put a token balance at each leaf. Traverse depth-first pre-order to accumulate the balance sequence.
```
      11
    /   \
   00   00
    \10  \1
    8    11
         / \
        3  7
Balance sequence: 8 3 7
```

**Example.** Consider that we want a minimal structure which includes account 1110, but also allows us to compute the merkle root. We also need hashes `a` and `b`, which we include as labels.
```
      01
     /  \
    a   00
         \1
         10
         / \
        3  b

Node label sequence excluding leaves: 01 00 10
Edge label sequence: 1
Balance sequence: 3
Hash sequence: a b
```

**Remark.** The hash sequence and label sequences are actually much more complicated than this example reveals. For example, the hash sequence must be encoded in depth-first post-order for the following algorithm to work, and a Merkle hash is required for each "missing" child of internal nodes, where "missing" is relative to the tree with all of the accounts. Generating a merkle proof in this form is the most complicated part of this repo. See the code for now. TODO find a simple explanation.

**Algorithm.** Merkleize a Merkle proof.
```
Input: Edge and Node label sequences for a tree with Optimization 2. Also balance sequence and hash sequence.
Output: Merkle root hash.
MERKLEIZE(current_prefix)
If length of current_prefix is full address, hash the address and balance, return the hash
Otherwise:
  Get next value from children pattern sequence.
    if 11: Recurse with 0 appended to current_prefix, which returns the left hash.
           Recurse with 1 appended to current_prefix, which returns the right hash.
           Return the hash of the left hash and right hash concatenated.
    if 01: Recurse with 0 appended to current_prefix, which returns the left hash.
           Get the next hash from the hash sequence, this is the left hash.
           Return the hash of the left hash and right hash concatenated.
    if 10: Recurse with 1 appended to current_prefix, which returns the right hash.
           Get the next hash from the hash sequence, this is the right hash.
           Return the hash of the left hash and right hash concatenated.
    if 00: Recurse with next edge label appended to current_prefix.
```


**Remark.** A merkle proof encoded this way can combine many merkle proofs (a "multiproof"), and there will be no duplicated hashes. TODO: explain and give example.


## Token Transactions

**Remark.** The contract can evaluate transactions between any of the accounts verified in the merkle proof. Each transaction is a signed message saying to send some tokens to a given address. Of course, there should be checks to prevent token underflow (i.e. negative balances).


## The Full Token Contract

**Algorithm.** Stateless merkle token state transition function.
```
INPUTS: (a) State Merkle root.
        (b) Node label sequence as in Optimizaiton 2.
        (c) Edge label sequence as in Optimizaiton 2.
        (d) Merkle hash sequence as in Optimization 2.
        (e) Balance sequence as in Optimization 2.
        (f) Transaction/Signature list, each prefixed by the sender's address's index in the ordered list of addresses of the current Merkle proof..
OUTPUT: New state merkle root.
MAIN()
1. Traverse (b) (with help from (c)) to get sorted list of addresses.
2. Verify all signatures.
3. Build final balance array by executing all transactions, verifying no balance underflow.
4. Compute previous state root and compute new state root by traversing (b) (with (c), (d), (e), and balances computed in 3.).
5. If computed previous root matches given previous root, update the state root with the computed new state root.
```

## Merkle Proof Sizes

**Remark.** Merkle proof sizes are known to be very large. Possible solutions: 
 - Experimentally, merkle proofs are 90% hashes. We use short hashes, like 160-bit blake2b hashes, which match the 160-bit security when generating Bitcoin and Ethereum addresses.
 - Allow different hash sizes in different subtrees, so say the left half of the tree will have shorter hashes and merkle proofs, but lower security.
 - Use different hash sizes at different part of tree. E.g. use longer hashes near leaves, since the hashes near the root are changing often so difficult to attack in time.
 - [Universal hashing](https://en.wikipedia.org/wiki/Universal_hashing) ensure low number of collisions in expectation. This may allow reducing hash length.
 - Associative and commutative hash functions to perform as much hashing off-chain as possible. Not aware of reasonable hash functions like this, maybe exponentiation using RSA modulus.
 - Succinct zero knowledge Merklization may allow omitting Merkle hashes.


## Contract Execution Speed

**Remark.** It is expensive to verify signatures, expensive to compute merkle roots, and expensive to hash. Some possible solutions:
 - We combine verify root and update root to a single pass over the hashes.
 - We use Ed25519 signatures because they hold speed records at the 128-bit security level, and can be batch processed for a 2x speedup.
 - We propose parallelism for both merkleization and signature verification.
 - Succinct zero knowledge proofs.


## Depth Attacks

**Remark.** A *depth attack* is when an attacker creates non-uniform depth in the tree to make merkle proofs long for some accounts. Possible solutions:
 - Self-balancing tree.
 - Hashing keys based on something difficult to control like the state root. Ethereum does something like this.
 - Economic solution: cost for account creation at a specific depth (maybe with a refund for account deletion).


## Hash Collision Attack

**Remark.** An attacker who finds a Merkle hash collision, with the new hash proving that they own a large number of tokens. Some possible solutions:
 - Long hashes. But none of the strong 160 bit hash functions have had published collisions yet, so 160-bits may be enough.
 - Adaptive hash length: start with short hashes, and upon proof of collision, increase hash length by two bytes and reMerklize the whole tree on-chain with the increased hash length.
 - Require cumulative balances alongside each Merkle hash, and hash this cumulative balance with each node. Th is constrains collisions because hashes must satisfy extra constraints to honor balance totals for each subtree.


## DoS attack

**Remark.** It may take a long time to verify the merkle root and signatures, so it may be necessary to charge for gas outside of the token. Or with a separatec 2-leaf block with one transaction.


## References

[Knuth, 1997] Knuth, Art of Computer Programming, Volume 1, 3rd ed.

[Katajainen and Makinen, 1990] Katajainen, Makinen. Tree Compression and Optimizatin With Applications, 1990. 


