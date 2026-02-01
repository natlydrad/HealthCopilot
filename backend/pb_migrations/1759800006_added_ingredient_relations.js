/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Add templateId - if parsed from meal template (Tier 3)
  // Note: This field is added after meal_templates collection is created
  collection.fields.addAt(13, new Field({
    "cascadeDelete": false,
    "collectionId": "pbc_meal_templates",
    "hidden": false,
    "id": "relation_template",
    "maxSelect": 1,
    "minSelect": 0,
    "name": "templateId",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "relation"
  }))

  // Add brandFoodId - if parsed from brand database (Tier 2)
  // Note: This field is added after brand_foods collection is created
  collection.fields.addAt(14, new Field({
    "cascadeDelete": false,
    "collectionId": "pbc_brand_foods",
    "hidden": false,
    "id": "relation_brand_food",
    "maxSelect": 1,
    "minSelect": 0,
    "name": "brandFoodId",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "relation"
  }))

  return txApp.save(collection)
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Rollback: remove relation fields
  collection.fields.removeById("relation_template")
  collection.fields.removeById("relation_brand_food")

  return txApp.save(collection)
})
