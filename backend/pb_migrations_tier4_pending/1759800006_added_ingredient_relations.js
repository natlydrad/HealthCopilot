/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Check if fields already exist using getAll() (safer than getById)
  const existingFields = collection.fields.getAll();
  const hasTemplateId = existingFields.some(f => f.id === "relation_template" || f.name === "templateId");
  const hasBrandFoodId = existingFields.some(f => f.id === "relation_brand_food" || f.name === "brandFoodId");

  // Add templateId - if parsed from meal template (Tier 3)
  // Note: This field is added after meal_templates collection is created
  // Skip if field already exists
  if (!hasTemplateId) {
    collection.fields.addAt(existingFields.length, new Field({
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
  }

  // Add brandFoodId - if parsed from brand database (Tier 2)
  // Note: This field is added after brand_foods collection is created
  // Skip if field already exists
  if (!hasBrandFoodId) {
    // Refresh fields list in case templateId was just added
    const currentFields = collection.fields.getAll();
    collection.fields.addAt(currentFields.length, new Field({
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
  }

  return txApp.save(collection)
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Rollback: remove relation fields
  collection.fields.removeById("relation_template")
  collection.fields.removeById("relation_brand_food")

  return txApp.save(collection)
})
