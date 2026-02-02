/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Add parsingStrategy field - tracks which parsing method was used
  // Check if field exists by trying to find it
  if (!collection.fields.getByName("parsingStrategy")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "select_parsing_strategy",
      "maxSelect": 1,
      "name": "parsingStrategy",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "select",
      "values": [
        "template",
        "brand_db",
        "history",
        "gpt",
        "manual",
        "cached"
      ]
    }))
  }

  // Add confidence score - 0.0 to 1.0
  if (!collection.fields.getByName("confidence")) {
    collection.fields.add(new Field({
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
  if (!collection.fields.getByName("parsingMetadata")) {
    collection.fields.add(new Field({
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

  return txApp.save(collection)
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Rollback: remove new fields
  collection.fields.removeById("select_parsing_strategy")
  collection.fields.removeById("number_confidence")
  collection.fields.removeById("json_parsing_metadata")

  return txApp.save(collection)
})
