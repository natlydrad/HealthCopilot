/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = new Collection({
    "id": "pbc_brand_foods",
    "name": "brand_foods",
    "type": "base",
    "system": false,
    "listRule": "1=1",  // Public read, admin write
    "viewRule": "1=1",
    "createRule": null,  // Admin only
    "updateRule": null,
    "deleteRule": null,
    "fields": [
      {
        "autogeneratePattern": "[a-z0-9]{15}",
        "hidden": false,
        "id": "text3208210256",
        "max": 15,
        "min": 15,
        "name": "id",
        "pattern": "^[a-z0-9]+$",
        "presentable": false,
        "primaryKey": true,
        "required": true,
        "system": true,
        "type": "text"
      },
      {
        "autogeneratePattern": "",
        "hidden": false,
        "id": "text_brand_name",
        "max": 0,
        "min": 0,
        "name": "brand",
        "pattern": "",
        "presentable": true,
        "primaryKey": false,
        "required": true,
        "system": false,
        "type": "text"
      },
      {
        "autogeneratePattern": "",
        "hidden": false,
        "id": "text_item_name",
        "max": 0,
        "min": 0,
        "name": "item",
        "pattern": "",
        "presentable": true,
        "primaryKey": false,
        "required": true,
        "system": false,
        "type": "text"
      },
      {
        "hidden": false,
        "id": "json_ingredients",
        "maxSize": 0,
        "name": "ingredients",
        "presentable": false,
        "required": true,
        "system": false,
        "type": "json"
      },
      {
        "hidden": false,
        "id": "number_total_calories",
        "max": null,
        "min": 0,
        "name": "totalCalories",
        "onlyInt": false,
        "presentable": false,
        "required": false,
        "system": false,
        "type": "number"
      },
      {
        "hidden": false,
        "id": "json_nutrition",
        "maxSize": 0,
        "name": "nutrition",
        "presentable": false,
        "required": false,
        "system": false,
        "type": "json"
      },
      {
        "hidden": false,
        "id": "json_metadata",
        "maxSize": 0,
        "name": "metadata",
        "presentable": false,
        "required": false,
        "system": false,
        "type": "json"
      },
      {
        "hidden": false,
        "id": "autodate2990389176",
        "name": "created",
        "onCreate": true,
        "onUpdate": false,
        "presentable": false,
        "system": false,
        "type": "autodate"
      },
      {
        "hidden": false,
        "id": "autodate3332085495",
        "name": "updated",
        "onCreate": true,
        "onUpdate": true,
        "presentable": false,
        "system": false,
        "type": "autodate"
      }
    ],
    "indexes": [
      "CREATE INDEX `idx_brand_foods_brand` ON `brand_foods` (`brand`)",
      "CREATE INDEX `idx_brand_foods_item` ON `brand_foods` (`item`)",
      "CREATE UNIQUE INDEX `idx_brand_foods_unique` ON `brand_foods` (`brand`, `item`)"
    ]
  });

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_brand_foods");

  return txApp.delete(collection);
});
