/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // Add parsingStrategy field - tracks which parsing method was used
  collection.fields.addAt(10, new Field({
    "hidden": false,
    "id": "select_parsing_strategy",
    "maxSelect": 1,
    "name": "parsingStrategy",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "select",
    "values": [
      "template",      // From meal template (Tier 3)
      "brand_db",      // From brand database (Tier 2)
      "history",       // From similar past meal (Tier 3)
      "gpt",           // From GPT Vision (current)
      "manual",        // User entered directly
      "cached"         // From parsing cache (Tier 4)
    ]
  }))

  // Add confidence score - 0.0 to 1.0 (Tier 4)
  collection.fields.addAt(11, new Field({
    "hidden": false,
    "id": "number_confidence",
    "max": 1,
    "min": 0,
    "name": "confidence",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  // Add parsingMetadata - flexible JSON for future parsing details
  collection.fields.addAt(12, new Field({
    "hidden": false,
    "id": "json_parsing_metadata",
    "maxSize": 0,
    "name": "parsingMetadata",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  }))

  // Update source field to include new parsing strategies
  // Note: This migration assumes source field already exists
  // We'll keep source for backward compatibility, parsingStrategy is the new field

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // Rollback: remove new fields
  collection.fields.removeById("select_parsing_strategy")
  collection.fields.removeById("number_confidence")
  collection.fields.removeById("json_parsing_metadata")

  return app.save(collection)
})
