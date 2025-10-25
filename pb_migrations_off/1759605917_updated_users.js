/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("_pb_users_auth_")

  // update collection data
  unmarshal({
    "createRule": "@request.auth.id = id",
    "deleteRule": "@request.auth.id = id",
    "listRule": "@request.auth.id = id",
    "updateRule": "@request.auth.id = id",
    "viewRule": "@request.auth.id = id"
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("_pb_users_auth_")

  // update collection data
  unmarshal({
    "createRule": "1=1",
    "deleteRule": "1=1",
    "listRule": "1=1",
    "updateRule": "1=1",
    "viewRule": "1=1"
  }, collection)

  return app.save(collection)
})
