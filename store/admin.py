from django.contrib import admin
from .models import Category, Product, ProductImage, ProductVariant, Review

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 2

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'stock', 'badge', 'is_active', 'is_featured']
    list_filter = ['category', 'badge', 'is_active', 'is_featured']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline, ProductVariantInline]
    list_editable = ['is_active', 'is_featured', 'stock']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating']