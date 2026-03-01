import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from inventory.models import Product, ProductSKU, Commodity, CommodityVariant, CommodityRate
from accounts.models import Cart, Wishlist
from decimal import Decimal
from django.utils import timezone

User = get_user_model()

def run_verification():
    print("Starting Verification...")

    # 1. Setup Data
    print("Setting up test data...")
    user, _ = User.objects.get_or_create(email="test@example.com", defaults={"full_name": "Test User", "is_verified": True})
    
    # Create Commodity
    gold, _ = Commodity.objects.get_or_create(code="gold", defaults={"name": "Gold", "category": "metal"})
    variant, _ = CommodityVariant.objects.get_or_create(commodity=gold, code="22k", defaults={"name": "22K Gold"})
    
    # Create Rate
    rate, _ = CommodityRate.objects.get_or_create(
        variant=variant, 
        effective_date=timezone.now().date(),
        defaults={"unit_price": Decimal("5000.00"), "is_active": True}
    )

    # Create Product & SKU
    product, _ = Product.objects.get_or_create(name="Test Ring", slug="test-ring")
    sku, _ = ProductSKU.objects.get_or_create(
        product=product, 
        sku_code="SKU-TEST-001",
        defaults={
            "price": Decimal("10000.00"),
            "weight": Decimal("2.0"),
            "stock_qty": 5,
            "commodity_variant": variant,
            "is_active": True
        }
    )
    # Ensure stock is 5
    sku.stock_qty = 5
    sku.save()

    client = APIClient()
    client.force_authenticate(user=user)

    # 2. Test Cart - Add Item
    print("\n[TEST] Add Item to Cart")
    response = client.post('/api/cart/add_item/', {'sku_id': sku.id, 'quantity': 2}, format='json')
    if response.status_code == 200:
        print("PASS: Item added to cart.")
        cart = Cart.objects.get(user=user)
        if cart.items.first().quantity == 2:
            print("PASS: Quantity is 2.")
        else:
            print(f"FAIL: Quantity mismatch. Expected 2, got {cart.items.first().quantity}")
    else:
        print(f"FAIL: Add item failed. {response.data}")

    # 3. Test Cart - Stock Validation
    print("\n[TEST] Stock Validation (Exceed Stock)")
    # Current in cart: 2. Stock: 5. Try adding 4 more (Total 6 > 5)
    response = client.post('/api/cart/add_item/', {'sku_id': sku.id, 'quantity': 4}, format='json')
    if response.status_code == 400 and "Insufficient stock" in str(response.data):
        print("PASS: Stock validation worked.")
    else:
        print(f"FAIL: Stock validation failed. Status: {response.status_code}, Data: {response.data}")

    # 4. Test Wishlist - Add
    print("\n[TEST] Add to Wishlist")
    # Clean wishlist
    Wishlist.objects.filter(user=user).delete()
    
    response = client.post('/api/wishlist/', {'sku_id': sku.id}, format='json')
    if response.status_code == 201:
        print("PASS: Added to wishlist.")
    else:
        print(f"FAIL: Add to wishlist failed. {response.data}")

    # 5. Test Wishlist - Move to Cart
    print("\n[TEST] Move to Cart")
    # Get wishlist item id
    wishlist_item = Wishlist.objects.get(user=user, sku=sku)
    response = client.post(f'/api/wishlist/{wishlist_item.id}/move_to_cart/')
    
    if response.status_code == 200:
        print("PASS: Moved to cart.")
        # Check cart quantity. Was 2, added 1 = 3.
        cart_item = Cart.objects.get(user=user).items.get(sku=sku)
        if cart_item.quantity == 3:
            print("PASS: Cart quantity updated to 3.")
        else:
            print(f"FAIL: Cart quantity mismatch. Expected 3, got {cart_item.quantity}")
        
        if not Wishlist.objects.filter(id=wishlist_item.id).exists():
             print("PASS: Wishlist item removed.")
        else:
             print("FAIL: Wishlist item not removed.")
    else:
        print(f"FAIL: Move to cart failed. {response.data}")

    print("\nVerification Complete.")

if __name__ == "__main__":
    run_verification()
