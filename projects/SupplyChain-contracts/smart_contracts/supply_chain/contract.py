from algopy import ARC4Contract, Global, Txn, UInt64, arc4, gtxn, op

HARVESTED = 0
PROCESSED = 1
PACKED = 2
FOR_SALE = 3
SOLD = 4
SHIPPED = 5
RECEIVED = 6
PURCHASED = 7

# Box key and value sizes
BOX_KEY_SIZE = 32
BOX_VALUE_SIZE = 64


class Item(arc4.Struct):
    farm_address: arc4.Address
    farm_name: arc4.String
    farm_info: arc4.String
    longitude: UInt64
    latitude: UInt64
    product_note: arc4.String
    state: UInt64
    price: UInt64

    @staticmethod
    def pad_string(s: str, length: int) -> bytes:
        """Pads a string to a fixed length with null bytes."""
        return s.encode().ljust(length, b"\x00")

    @staticmethod
    def serialize(item: "Item") -> bytes:
        """Serializes the item into a byte array."""
        return (
            item.farm_address.bytes
            + Item.pad_string(str(item.farm_name), 32)
            + Item.pad_string(str(item.farm_info), 32)
            + op.itob(int(item.longitude))
            + op.itob(int(item.latitude))
            + Item.pad_string(str(item.product_note), 32)
            + op.itob(int(item.state))
            + op.itob(int(item.price))
        )

    @staticmethod
    def deserialize(data: bytes) -> "Item":
        """Deserializes the byte array back into an Item object."""
        farm_address = arc4.Address(data[:32].hex())
        farm_name = arc4.String(data[32:64].rstrip(b"\x00").decode())
        farm_info = arc4.String(data[64:96].rstrip(b"\x00").decode())
        longitude = op.btoi(data[96:104])
        latitude = op.btoi(data[104:112])
        product_note = arc4.String(data[112:144].rstrip(b"\x00").decode())
        state = op.btoi(data[144:152])
        price = op.btoi(data[152:160])

        return Item(
            farm_address=farm_address,
            farm_name=farm_name,
            farm_info=farm_info,
            longitude=UInt64(int(longitude)),
            latitude=UInt64(int(latitude)),
            product_note=product_note,
            state=UInt64(int(state)),
            price=UInt64(int(price)),
        )


class SupplyChain(ARC4Contract):

    @arc4.abimethod
    def __init__(self) -> None:
        self.farmer = Global.zero_address
        self.distributor = Global.zero_address
        self.retailer = Global.zero_address
        self.consumer = Global.zero_address
        # self.item = BoxMap(arc4.Address, Item)

    @arc4.abimethod
    def add_item(
        self,
        item: Item,
        nonce: UInt64,
        xfer: gtxn.AssetTransferTransaction,
        mbr_pay: gtxn.PaymentTransaction,
    ) -> None:
        assert mbr_pay.sender == Txn.sender
        assert mbr_pay.receiver == Global.current_application_address

        box_key = Txn.sender.bytes + op.itob(xfer.xfer_asset.id) + op.itob(int(nonce))

        _length, box_exists = op.Box.length(box_key)
        assert not box_exists, "Box already exists for this item"

        assert xfer.sender == Txn.sender
        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.asset_amount > 0

        # Serialize the item
        serialized_item = Item.serialize(item)

        # Create the box with the serialized item size
        box_size = len(serialized_item)
        op.Box.create(box_key, box_size)

        # Store the serialized item in the box
        op.Box.replace(box_key, 0, serialized_item)

    # Retrieve item information from the Box
    @arc4.abimethod
    def get_item(self, upc: UInt64) -> UInt64:
        # Retrieve the item's Box using the UPC
        box_key = op.itob(upc)
        box_length, box_exists = op.Box.length(box_key)
        assert box_exists, "Box does not exist for this item"

        # Extract values from the Box (starting from byte 0)
        item_data = op.Box.extract(box_key, 0, BOX_VALUE_SIZE)

        # Extract specific fields (SKU and productID as an example)
        sku = op.btoi(item_data[:8])
        productID = op.btoi(item_data[8:16])

        # Return the SKU or other extracted value as needed
        return sku

    # Process the harvested item
    @arc4.abimethod
    def process_item(self, upc: UInt64) -> None:
        # Use Box to retrieve the item and process its state
        box_key = op.itob(upc)
        box_length, box_exists = op.Box.length(box_key)
        assert box_exists, "Box does not exist for this item"

        # Extract the current state
        current_state = op.btoi(
            op.Box.extract(box_key, 16, 8)
        )  # Assuming state is stored at byte 16

        # Ensure the current state is HARVESTED before processing
        assert current_state == HARVESTED, "Item is not in harvested state"

        new_state = op.itob(UInt64(PROCESSED))
        op.Box.replace(box_key, 16, new_state)

    # Farmer packs the item after processing
    @arc4.abimethod
    def pack_item(self, upc: UInt64) -> None:
        box_key = op.itob(upc)
        box_exists = op.Box.length(box_key)[1]
        assert box_exists, "Item does not exist"

        # Extract the item from Box
        item_data = op.Box.extract(box_key, 0, BOX_VALUE_SIZE)
        item_state = op.btoi(item_data[16:24])  # Assuming state is stored at byte 16

        # Ensure the item is in 'Processed' state
        assert item_state == UInt64(1), "Item's status is not processed"

        # Set the state to 'Packed'
        new_state = op.itob(UInt64(2))
        op.Box.replace(box_key, 16, new_state)  # Update item state to Packed

    # Farmer sells the item
    @arc4.abimethod
    def sell_item(self, upc: UInt64, price: UInt64) -> None:
        box_key = op.itob(upc)
        box_exists = op.Box.length(box_key)[1]
        assert box_exists, "Item does not exist"

        # Extract the item from Box
        item_data = op.Box.extract(box_key, 0, BOX_VALUE_SIZE)
        item_state = op.btoi(item_data[16:24])  # Assuming state is stored at byte 16

        # Ensure the item is in 'Packed' state
        assert item_state == UInt64(2), "Item's status is not packed"

        # Set the state to 'For Sale' and set the price
        new_state = op.itob(UInt64(3))  # For Sale state
        op.Box.replace(box_key, 16, new_state)  # Update item state to For Sale
        op.Box.replace(box_key, 24, op.itob(price))  # Store the price

    # Distributor buys the item
    @arc4.abimethod
    def buy_item(self, upc: UInt64) -> None:
        box_key = op.itob(upc)
        box_exists = op.Box.length(box_key)[1]
        assert box_exists, "Item does not exist"

        # Extract the item from Box
        item_data = op.Box.extract(box_key, 0, BOX_VALUE_SIZE)
        item_state = op.btoi(item_data[16:24])  # Assuming state is stored at byte 16

        # Ensure the item is in 'For Sale' state
        assert item_state == UInt64(3), "Item is not for sale"

        # Update owner to distributor and set the state to 'Sold'
        new_state = op.itob(UInt64(4))  # Sold state
        op.Box.replace(box_key, 16, new_state)  # Update state
        op.Box.replace(box_key, 32, Txn.sender.bytes)  # Update owner to distributor

    # Distributor ships the item
    @arc4.abimethod
    def ship_item(self, upc: UInt64) -> None:
        box_key = op.itob(upc)
        box_exists = op.Box.length(box_key)[1]
        assert box_exists, "Item does not exist"

        # Extract the item from Box
        item_data = op.Box.extract(box_key, 0, BOX_VALUE_SIZE)
        item_state = op.btoi(item_data[16:24])  # Assuming state is stored at byte 16

        # Ensure the item is in 'Sold' state
        assert item_state == UInt64(4), "Item is not sold"

        # Set the state to 'Shipped'
        new_state = op.itob(UInt64(5))  # Shipped state
        op.Box.replace(box_key, 16, new_state)  # Update state to Shipped

    # Retailer receives the item
    @arc4.abimethod
    def receive_item(self, upc: UInt64) -> None:
        box_key = op.itob(upc)
        box_exists = op.Box.length(box_key)[1]
        assert box_exists, "Item does not exist"

        # Extract the item from Box
        item_data = op.Box.extract(box_key, 0, BOX_VALUE_SIZE)
        item_state = op.btoi(item_data[16:24])  # Assuming state is stored at byte 16

        # Ensure the item is in 'Shipped' state
        assert item_state == UInt64(5), "Item is not shipped"

        # Set the state to 'Received' and update owner to retailer
        new_state = op.itob(UInt64(6))  # Received state
        op.Box.replace(box_key, 16, new_state)  # Update state to Received
        op.Box.replace(box_key, 32, Txn.sender.bytes)  # Update owner to retailer

    # Consumer purchases the item
    @arc4.abimethod
    def purchase_item(self, upc: UInt64) -> None:
        box_key = op.itob(upc)
        box_exists = op.Box.length(box_key)[1]
        assert box_exists, "Item does not exist"

        # Extract the item from Box
        item_data = op.Box.extract(box_key, 0, BOX_VALUE_SIZE)
        item_state = op.btoi(item_data[16:24])  # Assuming state is stored at byte 16

        # Ensure the item is in 'Received' state
        assert item_state == UInt64(6), "Item is not received"

        # Set the state to 'Purchased' and update owner to consumer
        new_state = op.itob(UInt64(7))  # Purchased state
        op.Box.replace(box_key, 16, new_state)  # Update state to Purchased
        op.Box.replace(box_key, 32, Txn.sender.bytes)  # Update owner to consumer

    # Set price for item
    # @arc4.abimethod
    # def set_price(
    #     self, asset: UInt64, nonce: arc4.UInt64, unitary_price: arc4.UInt64
    # ) -> None:
    #     box_key = Txn.sender.bytes + nonce.bytes + op.itob(asset)

    #     op.Box.replace(box_key, 8, op.itob(op.btoi(unitary_price)))
