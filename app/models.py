import maya
from graphql import GraphQLError
from py2neo import Graph
from py2neo.ogm import GraphObject, Property, RelatedTo

from app import settings


graph = Graph(
    host=settings.NEO4J_HOST,
    port=settings.NEO4J_PORT,
    user=settings.NEO4J_USER,
    password=settings.NEO4J_PASSWORD,
)


class BaseModel(GraphObject):
    """
    Implements some basic functions to guarantee some standard functionality
    across all models. The main purpose here is also to compensate for some
    missing basic features that we expected from GraphObjects, and improve the
    way we interact with them.
    """

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    @property
    def all(self):
        return self.select(graph)

    def save(self):
        graph.push(self)


class Product(BaseModel):
    __primarykey__ = 'name'

    name = Property()
    brand = Property()
    category = Property()

    def as_dict(self):
        return {
            'name': self.name,
            'brand': self.brand,
            'category': self.category
        }

    def fetch(self):
        return self.select(graph, self.name).first()


class Store(BaseModel):
    name = Property()
    address = Property()

    products = RelatedTo('Product', 'SELLS')
    receipts = RelatedTo('Product', 'EMITTED')

    def fetch(self, _id):
        return Store.select(graph, _id).first()

    def fetch_by_name_and_address(self):
        return Store.select(graph).where(
            f'_.name = "{self.name}" AND _.address = "{self.address}"'
        ).first()

    def fetch_products(self):
        return [{
            **product[0].as_dict(),
            **product[1]
        } for product in self.products._related_objects]

    def as_dict(self):
        return {
            '_id': self._GraphObject__ogm.node._Entity__remote._id,
            'name': self.name,
            'address': self.address
        }


class Receipt(BaseModel):
    total_amount = Property()
    timestamp = Property()

    products = RelatedTo('Product', 'HAS')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if kwargs.get('validate', False):
            self.__validate_timestamp()

    def as_dict(self):
        return {
            '_id': self._GraphObject__ogm.node._Entity__remote._id,
            'total_amount': self.total_amount,
            'timestamp': maya.parse(self.timestamp)
        }

    def fetch(self, _id):
        return self.select(graph, _id).first()

    def fetch_products(self):
        return [{
            **product[0].as_dict(),
            **product[1]
        } for product in self.products._related_objects]

    def __validate_timestamp(self):
        try:
            maya.parse(self.timestamp, day_first=True, year_first=False)
        except Exception:
            raise GraphQLError(
                'The timestamp you provided is not within the format: "dd/mm/yyyy hh:mm"'
            )


class Customer(BaseModel):
    __primarykey__ = 'email'
    name = Property()
    email = Property()

    receipts = RelatedTo('Receipt', 'HAS')
    stores = RelatedTo('Store', 'GOES_TO')

    def fetch(self):
        customer = self.select(graph, self.email).first()
        if customer is None:
            raise GraphQLError(f'"{self.email}" has not been found in our customers list.')

        return customer

    def as_dict(self):
        return {
            'email': self.email,
            'name': self.name
        }

    def __verify_products(self, products):
        _total_amount = 0
        for product in products:
            _product = Product(name=product.get('name')).fetch()
            if _product is None:
                raise GraphQLError(f'"{product.name}" has not been found in our products list.')

            _total_amount += product['price'] * product['amount']
            product['product'] = _product
        return products, _total_amount

    def __verify_receipt(self, receipt):
        customer_properties = f":Customer {{email: '{self.email}'}}"
        receipt_properties = f":Receipt {{timestamp: '{receipt.timestamp}', total_amount:{receipt.total_amount}}}"
        existing_receipts = graph.run(
            f"MATCH ({customer_properties})-[relation:HAS]-({receipt_properties}) RETURN relation").data()

        if existing_receipts:
            raise GraphQLError("The receipt you're trying to submit already exists.")

    def __link_products(self, products, total_amount, timestamp):
        receipt = Receipt(total_amount=total_amount, timestamp=timestamp, validate=True)
        self.__verify_receipt(receipt)

        for item in products:
            receipt.products.add(item.pop('product'), properties=item)

        return receipt

    def __verify_store(self, store):
        _store = Store(**store).fetch_by_name_and_address()
        if _store is None:
            raise GraphQLError(f"The store \"{store['name']}\" does not exist in our stores list.")

        return _store

    def __add_links(self, store, receipt):
        store.receipts.add(receipt)
        self.stores.add(store)
        self.receipts.add(receipt)

    def submit_receipt(self, products, timestamp, store):
        self.__add_links(
            self.__verify_store(store),
            self.__link_products(*self.__verify_products(products), timestamp)
        )

        self.save()
