/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // Add parsingStrategy field - tracks which parsing method was used
  // Skip if field already exists
  const existingFields = collection.fields.getAll();
  const hasParsingStrategy = existingFields.some(f => f.name === "parsingStrategy");
  
  if (!hasParsingStrategy) {
    collection.fields.addAt(existingFields.length, new Field({
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
    ]}))
  }

  // Add confidence score - 0.0 to 1.0 (Tier 4)
  // Skip if field already exists
  const hasConfidence = existingFields.some(f => f.name === "confidence");
  
  if (!hasConfidence) {
    collection.fields.addAt(existingFields.length, new Field({
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
  }

  // Add parsingMetadata - flexible JSON for future parsing details
  // Skip if field already exists
  const hasParsingMetadata = existingFields.some(f => f.name === "parsingMetadata");
  
  if (!hasParsingMetadata) {
    collection.fields.addAt(existingFields.length, new Field({
    "hidden": false,
    "id": "json_parsing_metadata",
    "maxSize": 0,
    "name": "parsingMetadata",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  }))
  }

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
