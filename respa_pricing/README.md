Initial file to document what has been done so far for project handover.

Initial specification can be found at: https://intra.anders.fi/pages/viewpage.action?pageId=113705139

Project configuration can also be found at: 


respa_pricing app holds the most of the logic related to tiered pricing. Respa supports the paid resources in addition to
free resources. Tiered pricing is the feature Tampere City wanted where the price of the same resource could be 
different based on who is reserving (UserGroup) the resource or for what purpose (EventType) the resource is being
reserved. E.g. The price for resource X reserved by the employees of Tampere City for personal use could cost one 
price while the same resource reserved by Students could cost another price.


The logic behind the amount of price could still change but for now following rules apply.

When user makes reservation in the varaamo (frontend), the usergroup field is required. EventType is an 
optional form field. When the usergroup and eventtype is selected, price is automatically calculated. The logic
for price calcualtion is:
* Always choose the higher price source (UserGroup/EventType) for price and lower vat source (UserGroup/EventType).
  E.g. UserGroup X                      EventType Y
       price_before_tax = 10            price_before_tax = 20
       tax_percentage = 14              tax_percentage = 24
  
    If the user in Varaamo selects 'X' as user group and doesn't select event type, then total_price = 10 + 14% of 10
    If the user in Varaamo selects 'X' as user group and 'Y' as event type, then we select eventtype Y for price
    as (20 > 10) and usergrop 'X' for vat as (14 < 24). So the total_price = 20 + 14% of 20.

  
  
* If any of the selected item (usergroup/eventtype) has 0 price, that price should be take precedence.


All the price related fields (price, tax_percentage...) are moved from Product model (payments app) to 
UserGroup and EventType models (respa_pricing). A pricelist has usergroup and eventtype as foreign keys. When a
price list is attached to a resource, the products are created from usergroup and evernttype. These products
needs to be synced with Ceepos before deploying to production.

When the pricelist is changed in resource, old products are archived and new ones are created if they don't
exist.

# Process to create pricelist
Everthing is created in django admin now. Later event type and user group related items will be moved to
respa Admin. In order to create pricelist follow these steps:

1. Create the pricelist. It only requires name.
2. Create usergroups
3. Create eventtypes
4. Create event price list item
5. Create user group price list item

Finally, assign the created pricelist to resource. The resource should not be free to use when pricelist
is assigned to resource.


# How is price determined ?
When frontend makes request to get resource. Two new serializer fields are added to ResourceSerializer.
`pricing_user_group` and `pricing_event_group` . These are the usergroups and event types from a 
pricelist that is attached to a resource. 
When user selects the pricing group or event type, a request is made to `/v1/resource/get_price` 
that computes the price and returns to frontend.
