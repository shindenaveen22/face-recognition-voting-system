import hashlib
import time
import json
import os


class Block:
    def __init__(self, index, voter_id, candidate, previous_hash):
        self.index = index
        self.timestamp = time.time()
        self.voter_id = voter_id
        self.candidate = candidate
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "voter_id": self.voter_id,
            "candidate": self.candidate,
            "previous_hash": self.previous_hash
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()


class Blockchain:
    def __init__(self):
        self.data_file = "blockchain_data.json"
        self.chain = []
        self.voters = set()

        if not self.load_from_file():
            self.chain = [self.create_genesis_block()]
            self.voters = set()

    def create_genesis_block(self):
        return Block(0, "Genesis", "None", "0")

    def get_latest_block(self):
        return self.chain[-1]

    def add_vote(self, voter_id, candidate):
        # Check if this specific voter ID has already voted
        if voter_id in self.voters:
            return False, f"Voter ID '{voter_id}' has already cast a vote. Please use a unique ID for each person."

        previous_block = self.get_latest_block()
        new_block = Block(len(self.chain), voter_id,
                          candidate, previous_block.hash)

        # Simple validation before adding
        if self.is_block_valid(new_block, previous_block):
            self.chain.append(new_block)
            self.voters.add(voter_id)
            self.save_to_file()
            return True, "Vote recorded successfully."
        return False, "Invalid block data."

    def save_to_file(self):
        data = self.get_chain_data()
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=4)

    def load_from_file(self):
        if not os.path.exists(self.data_file):
            return False
        try:
            with open(self.data_file, 'r') as f:
                chain_data = json.load(f)
                self.chain = []
                self.voters = set()
                for b_data in chain_data:
                    block = Block(
                        b_data['index'],
                        b_data['voter_id'],
                        b_data['candidate'],
                        b_data['previous_hash']
                    )
                    block.timestamp = b_data['timestamp']
                    block.hash = b_data['hash']
                    self.chain.append(block)
                    if block.voter_id != "Genesis":
                        self.voters.add(block.voter_id)
                return True
        except Exception as e:
            print(f"Error loading blockchain: {e}")
            return False

    def is_block_valid(self, new_block, previous_block):
        if previous_block.index + 1 != new_block.index:
            return False
        if previous_block.hash != new_block.previous_hash:
            return False
        if new_block.calculate_hash() != new_block.hash:
            return False
        return True

    def is_chain_valid(self):
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i-1]
            if not self.is_block_valid(current_block, previous_block):
                return False
        return True

    def reset_chain(self):
        self.chain = [self.create_genesis_block()]
        self.voters = set()
        self.save_to_file()

    def get_results(self):
        results = {}
        # Skip genesis block
        for block in self.chain[1:]:
            results[block.candidate] = results.get(block.candidate, 0) + 1
        return results

    def get_chain_data(self):
        return [{
            "index": b.index,
            "timestamp": b.timestamp,
            "voter_id": b.voter_id,
            "candidate": b.candidate,
            "previous_hash": b.previous_hash,
            "hash": b.hash
        } for b in self.chain]
