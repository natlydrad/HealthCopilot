/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_695162881")

  // update collection data
  unmarshal({
    "createRule": "@request.auth.id = user",
    "deleteRule": "@request.auth.id = user",
    "listRule": "@request.auth.id = user",
    "updateRule": "@request.auth.id = user",
    "viewRule": "@request.auth.id = user"
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_695162881")

  // update collection data
  unmarshal({
    "createRule": "@request.auth.id != \"\"",
    "deleteRule": "@request.auth.id != \"\"",
    "listRule": "@request.auth.id != \"\"",
    "updateRule": "@request.auth.id != \"\"",
    "viewRule": "@request.auth.id != \"\""
  }, collection)

  return app.save(collection)
})
