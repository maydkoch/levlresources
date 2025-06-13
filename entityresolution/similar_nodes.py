# pip3 install neo4j-driver
# python3 example.py

from neo4j import GraphDatabase, basic_auth

URI = "neo4j+ssc://1b551888.databases.neo4j.io"
AUTH = ("neo4j", "MU_rxscxE2q4BSFgP3Fj5MjnAJtvRLL_hlPbfQH5uZI")
driver = GraphDatabase.driver(URI, auth=AUTH)

cypher_query = '''
MATCH (a)
MATCH (b)
// not the same user
WHERE a <> b

// names
WITH a, b, a.name AS name1, b.name AS name2

// compute different similiarities
WITH *,
toInteger(apoc.text.sorensenDiceSimilarity(name1, name2) * 100) AS nameSimilarity

// filter
WHERE nameSimilarity >= 90

RETURN name1, name2, nameSimilarity

ORDER BY nameSimilarity DESC
'''

with driver.session() as session:
  result = session.run(cypher_query)
  records = [dict(record) for record in result]
  print(records)

driver.close()
