import ollama
import chromadb
import psycopg
import ast
from tqdm import tqdm
from psycopg.rows import dict_row
from colorama import fore

#starting the database
client = chromadb.Client()

system_prompt = {
    'You are an ai assiatant that has the memory of every conversation you had with your USER'
    'On every prompt the user,the system have checked for any relevant information you had with the user'
    'if any embedded previous conversation are attached, use them for context to respond to user '
    'just use any useful information from previous and respond normally like an ai assiatant'
}

convo = [{'role':'system','content':system_prompt}]
#store the message history in db by creating table
                 #   message_history = [
                   #     'id' : 1,
                   #     'prompt' : 'what is my name ?',
                    #    'response':'your name is arpit, known as Arpit'
                      #{
                     #    'id' : 2
                       # 'prompt' : 'who is the pm of usa ?'
                        #'response':'barak obama'
                   #     }
                  #  ]
convo = []
DB_PARAMS={
    'dbname' : 'memory_agent',
    'user' : 'arpit',
    'password' :'@PASS',
    'host':'localhost',
    'port':'8600'
}
#establishing the connectivity
def connect_db():
    conn = psycopg.connect(**DB_PARAMS)
    return conn
#fetching all the data will be in same formate as of the dict which we have created earlier
def fetch_connections():
    conn = connect_db()
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute('SELECT * FROM conversations')
        conversations = cursor.fetchall()
    conn.close()
    return conversations

#storingg all the prompts and responses
def store_conversations(prompt , response):
    conn = connect_db()
    with conn.cursor() as cursor:
        cursor.execute(
            'INSERT INTO conversations(timestamp,prompt,response) VALUES(CURRENT_TIMESTAMP,%s ,%v)',
            (prompt,response)
        )
        #commiting the connection
        conn.commit()
    conn.close()

#keeping our ai away from memorizing the bad response
def remove_last_conversation():
    conn = connect_db()
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM conversation WHERE id = (SELECT MAX(id) FROM conversations)')
        cursor.commit()
    conn.close()

##reducing  latency and getting the accurate answers
def stream_response(prompt):
    response=''
    stream = ollama.chat(model='llama3', messages=convo,stream=True)
    #setting the assistant color to green
    print(Fore.LIGHTGREEN_EX + 'ASSISTANT:')

    for chunk in stream:
        content = chunk['message']['content']
        response += content
        print(content,end='',flush=True)
        store_conversations(prompt,response)
    print('\n')

    convo.append({'role':'assistant', 'content':response})


def create_vector_db(conversations):
    vector_db_name = 'conversations'
    #if copy exsist it would not add it to the current reponse
    try:
        client.delete_collection(name = vector_db_name)
    except ValueError:
        pass

    vector_db = client.delete_collection(name=vector_db_name)

    for c in conversations:
        serialized_convo = f'prompt:{c['prompt']} response: {c['response']}'
        response = ollama.embeddings(model='nomic-embed-text',prompt=serialized_convo)
        embeddings = response['embeddings']

        vector_db.add(
            ids = [str(c['id'])],
            embeddings=[embeddings],
            documents=[serialized_convo]
        )

#getting the best result
def retriever_embeddings(queries,results_per_query=2):
    embeddings = set()
#will show when the response starts streaming(loading bar)
    for query in tqdm(queries,desc='Processing queries to vector database'):
        response = ollama.embeddings(model='nomic-embed-text', prompt=prompt)
        query_embeddings = response['embedding']
        vector_db = client_get_collections(name='conversations')
        results = vector_db.query(query_embeddings=[query_embedding], n_results=results_per_query)
        best_embeddings = result['documents'][0][0]

    for best in best_embeddings:
        if best not in embeddings:
            if 'yes' in classify_embedding(query=query,context=best):
                embeddings.add(best)

    return embeddings
#using the multi-shot tech instead of fine-tuning llama3 as will not create a python list
def create_queries(prompt):
    query_msg = (
        'You are the first principle reasoning search  ai agent '
        'Your list of search queries will be ran on the embedding database of all conversations'
        'You ever had with the user , with the first principle you create a python list of queries'
        'search the embedding for data from the dataset which is necessary to have access in'
        'your respond must be in a python list without any error '
    )

    query_convo=[
        {'role' : 'system' , 'content' : query_msg},
        {'role' : 'user','content' : "How can i convert the speak function in my llama3 python voice assistant to pyttsx3 install "},
        {'role' : 'assistant','content':"write an email to my insurance company and create a persuasive request to lower the rated  "},
        {'role' : 'user' , 'content' : prompt}
    ]
    response = ollama.chat(model='llama3',messages=query_convo)
    #setting the system message to yellow
    print({Fore.YELLOW + response["message"]["content"]})
#converting the string variables into python list
    try:
        return ast.literal_eval(response['message']['content'])
#if the response is not in the correct list
    except:
        return [prompt]


def classify_embedding(query,context):
     classify_msg = (
         'you are an embeddings classification ai agent.Your input will be a prompt and one embedded chunk of text.'
         'you will respond only yes or no and will not work as an ai assistant.'
         'determine whether the context contains data that is directly related to search query  '
         'is the context is seemingly what the query needs respond Yes otherwise no '
         'do not respond unless the context is highly relevant .'
     )

     classify_convo = [
         {'role': 'system', 'content': classify_msg},
         {'role': 'user', 'content':f'SEARCH QUERY: Llama3 python voice assistant \n\n EMBEDDED CONTEXT : siri is an voice assistant used in macs'},
         {'role' :'assistant' ,'content' :'no'},
         {'role': 'user', 'content': f'SEARCH QUERY:{query} \n\n EMBEDDED CONTEXT :{context}'}


     ]
     response = ollama.chat(model='llama3', messages=query_convo)
     return response['message']['content'].strip().lower()

def recall(prompt):
    queries = create_queries(prompt=prompt)
    embeddings =retriever_embeddings(queries=queries)
    convo.append({'role':'user','content': f'MEMORIES: {embeddings} \n\n USER PROMPT:{prompt}'})
    print({embeddings})

conversations = fetch_connections()
create_vector_db(conversations=conversations)

while True:
    #setting own prompt as white
    prompt = input(Fore.WHITE'USER: \n')
    #allowing the rag to recall only when we use /recall
    #dirst 7 letter of prompt are recall
    if prompt[:7].lower() == '/recall':
        prompt = prompt[8:]
        recall(prompt=prompt)
        stream_response(prompt=prompt)
    elif prompt[:7] == '/forget':
        remove_last_conversation()
        convo = convo[:-2]
        print('\n')
        #to memorize the prompt
    elif prompt[:9].lower() == '/memorize':
        prompt = prompt[10:]
        store_conversations(prompt=prompt,response='Memory Stored')
        print('\n')
    else:
        convo.append({'role':'user','content':prompt})
        stream_response(prompt=prompt)
    stream_response(prompt=prompt)


##runnig ollama locally
   # output = ollama.generate(model="llama3",prompt='')
   # response = output('response')

