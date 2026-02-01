/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = new Collection({
    "id": "pbc_parsing_cache",
    "name": "parsing_cache",
    "type": "base",
    "system": false,
    "listRule": "1=1",  // Public read
    "viewRule": "1=1",
    "createRule": null,  // System only
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
        "id": "text_meal_text",
        "max": 0,
        "min": 0,
        "name": "mealText",
        "pattern": "",
        "presentable": false,
        "primaryKey": false,
        "required": false,
        "system": false,
        "type": "text"
      },
      {
        "hidden": false,
        "id": "text_meal_hash",
        "max": 64,
        "min": 64,
        "name": "mealHash",
        "pattern": "^[a-f0-9]{64}$",
        "presentable": false,
        "primaryKey": false,
        "required": true,
        "system": false,
        "type": "text"
      },
      {
        "hidden": false,
        "id": "json_parsed_ingredients",
        "maxSize": 0,
        "name": "parsedIngredients",
        "presentable": false,
        "required": true,
        "system": false,
        "type": "json"
      },
      {
        "hidden": false,
        "id": "select_model_used",
        "maxSelect": 1,
        "name": "modelUsed",
        "presentable": false,
        "required": false,
        "system": false,
        "type": "select",
        "values": [
          "gpt-4o-mini",
          "gpt-4-vision",
          "gpt-4o"
        ]
      },
      {
        "hidden": false,
        "id": "number_cost_usd",
        "max": null,
        "min": 0,
        "name": "costUsd",
        "onlyInt": false,
        "presentable": false,
        "required": false,
        "system": false,
        "type": "number"
      },
      {
        "hidden": false,
        "id": "number_hit_count",
        "max": null,
        "min": 0,
        "name": "hitCount",
        "onlyInt": true,
        "presentable": false,
        "required": false,
        "system": false,
        "type": "number"
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
      "CREATE UNIQUE INDEX `idx_parsing_cache_hash` ON `parsing_cache` (`mealHash`)",
      "CREATE INDEX `idx_parsing_cache_hits` ON `parsing_cache` (`hitCount`)"
    ]
  });

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_parsing_cache");

  return txApp.delete(collection);
});
