import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import secrets # api key

import traceback

import logger.logger as logger
import security.envManager as envManager
from security.encrypter import check_password_hash
import db.object as object
import db.jsonBuilder as jsonBuilder

POSTGRESQL_DB = envManager.read_postgresql_db()
POSTGRESQL_USER = envManager.read_postgresql_user()
POSTGRESQL_PASSWORD = envManager.read_postgresql_password()
POSTGRESQL_HOST = envManager.read_postgresql_host()
POSTGRESQL_PORT = envManager.read_postgresql_port()

conn = psycopg2.connect(dbname=POSTGRESQL_DB, user=POSTGRESQL_USER, password=POSTGRESQL_PASSWORD, host=POSTGRESQL_HOST, port=POSTGRESQL_PORT) 

def exist():
    
    cursor = conn.cursor()

    cursor.execute("select exists(select * from information_schema.tables where table_name=%s)", ('users',))
    bool = cursor.fetchone()[0]

    cursor.close()

    return bool


def init(): # init del database

    cursor = conn.cursor()

    POSTGRESQL_INIT_SCRIPT = envManager.read_postgresql_init_script()

    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)     

    logger.fromDatabase("INIT DEL DATABASE ESEGUITO")

    cursor.execute(POSTGRESQL_INIT_SCRIPT)

    cursor.close()

def clientDB_init(user_id):

    handle = user_group_channel_fromID_toHandle(user_id)

    response = {'type':'init','init':'False'}
    
    cursor = conn.cursor()

    QUERY = f"SELECT email,name,surname FROM public.users WHERE user_id='{user_id}'"
    
    try:
        logger.fromDatabase(QUERY)

        cursor.execute(QUERY)
        result = cursor.fetchone()
        cursor.close()

        email = result[0]
        name = result[1]
        surname = result[2]

    except:
        logger.logDebug(str(traceback.format_exc()))
        cursor.close()
        return response
    
    # get chat information

    chats = []

    cursor = conn.cursor()

    QUERY = f"SELECT chat_id,user1,user2 FROM public.chats WHERE user1={user_id} OR user2={user_id}"
    
    try:
        logger.fromDatabase(QUERY)

        cursor.execute(QUERY)
        resultChat = cursor.fetchall()

        for rowChat in resultChat:
            chat_id = str(rowChat[0])

            if str(rowChat[1]) == user_id:
                user = user_group_channel_fromID_toHandle(str(rowChat[2]))
            else:
                user = user_group_channel_fromID_toHandle(str(rowChat[1]))
            
            # get messages info

            messages = []

            QUERY = f"SELECT message_id,text,sender,date FROM public.messages WHERE chat_id={chat_id}"

            try:
                logger.fromDatabase(QUERY)

                cursor.execute(QUERY)
                resultMessage = cursor.fetchall()

                for rowMessage in resultMessage:

                    message = object.MessageJson(str(rowMessage[0]),chat_id,rowMessage[1],rowMessage[2],rowMessage[3])
                    messages.append(message)
            
            except:
                logger.logDebug(str(traceback.format_exc()))
                cursor.close()
                return response

            chat = object.ChatJson(chat_id,user,messages)
            chats.append(chat)

    except:
        logger.logDebug(str(traceback.format_exc()))
        cursor.close()
        return response

    # get groups information TDB

    groups = []

    # get channels information TDB

    channels = []

    cursor.close()

    return jsonBuilder.init_json(handle,email,name,surname,chats,groups,channels)

def get_userID_from_ApiKey(api_key):

    cursor = conn.cursor()

    QUERY = f"SELECT user_id FROM public.apiKeys WHERE api_key='{api_key}'"
    
    # fetch database for api_key
    try:
        logger.fromDatabase(QUERY)

        cursor.execute(QUERY)
        result = cursor.fetchone()
        cursor.close()

        user_id = str(result[0])

    except:
        logger.fromDatabase("No API Key found!")
        logger.logDebug(str(traceback.format_exc()))
        cursor.close()
        return None
    
    return user_id

def get_userHandle_from_apiKey(api_key):

    user_handle = None

    user_id = get_userID_from_ApiKey(api_key)

    if user_id == None:
        return None

    user_handle = user_group_channel_fromID_toHandle(user_id)

    # return handle to main (None = API_KEY non esiste [NON AUTORIZZATO] , negli altri casi ritorna l`handle dello user che ha eseguito la richiesta [viene anche utilizzato per il log] )

    return user_handle



def user_group_channel_fromID_toHandle(id):

    cursor = conn.cursor()

    QUERY = f"SELECT handle FROM public.handles WHERE user_id = '{id}' OR group_id = '{id}' OR channel_id = '{id}'"

    logger.fromDatabase(QUERY)

    cursor.execute(QUERY)

    # fetch database for handle with id

    

    try:
        result = cursor.fetchone()
        handle = result[0]
    except:
        logger.logDebug("ID not found"+str(traceback.format_exc()))
    cursor.close()

    # return only handle of the requested id

    return handle

def user_group_channel_fromHandle_toID(handle):

    cursor = conn.cursor()

    QUERY = f"SELECT user_id,group_id,channel_id FROM public.handles WHERE handle = '{handle}'"

    logger.fromDatabase(QUERY)

    cursor.execute(QUERY)

    # fetch database for IDs with handle

    result = cursor.fetchone()

    cursor.close()

    # return only id of the requested handle

    try:
        if result[0] != None: # user_id
            return str(result[0])
        elif result[1] != None: # group_id
            return str(result[1]) 
        elif result[2] != None: # channel_id
            return str(result[2])
    except:
        logger.logDebug(str(traceback.format_exc()))
        return None



def check_handle_availability(handle): # done

    cursor = conn.cursor()

    confirmation = False

    QUERY = f"SELECT handle FROM public.handles WHERE handle = '{handle}'"

    logger.fromDatabase(QUERY)

    cursor.execute(QUERY)

    # fetch database for handle (it should only be 1)
    result = cursor.fetchone()

    if result == None:
        confirmation = True
    
    cursor.close()

    # true: available | false: used

    return confirmation


    
def add_user_toDB(user): # aggiungi API key

    cursor = conn.cursor()

    confirmation = True

    api_key = secrets.token_urlsafe(256)

    #####################
#   AGGIUNGI CONTROLLI PER OGNI PARAMETRO (no duplicazione)
    ####################

    logger.fromDatabase("Check API duplicata...")
    while(get_userHandle_from_apiKey(api_key) != None): # check if api key is duplicated (i think its impossibile but, better safe than sorry)
        logger.fromDatabase("API Key duplicata, ne genero una nuova")
        api_key = secrets.token_urlsafe(256)

    QUERY = f"with new_user as (INSERT INTO public.users(email,name,surname,password) VALUES('{user.email}','{user.name}','{user.surname}','{user.password}') RETURNING user_id), new_handle AS (INSERT INTO public.handles(user_id,handle) VALUES((SELECT user_id FROM new_user),'{user.handle}')) INSERT INTO public.apiKeys(user_id,api_key) VALUES((SELECT user_id FROM new_user),'{api_key}')"
    logger.fromDatabase(QUERY)

    try:
        cursor.execute(QUERY)
        conn.commit()
    except:
        logger.logDebug(str(traceback.format_exc()))
        confirmation = False
    
    cursor.close()

    return confirmation

def check_userExistence_fromEmail(email):

    cursor = conn.cursor()

    confirmation = True

    QUERY = f"SELECT email FROM public.users WHERE email = '{email}'"

    logger.fromDatabase(QUERY)

    try:
        cursor.execute(QUERY)
        result = cursor.fetchone()
        if result == None:
            confirmation = False
    except:
        logger.logDebug(str(traceback.format_exc()))
        confirmation = False

    # fetch database for e-mails (it should only be 1)
    
    cursor.close()

    # true: email already used | false: email not used

    return confirmation

def check_userExistence_fromHandle(handle):

    cursor = conn.cursor()

    confirmation = True

    QUERY = f"SELECT user_id FROM public.handles WHERE handle = '{handle}'"

    logger.fromDatabase(QUERY)

    cursor.execute(QUERY)

    # fetch database for user_id (it should only be 1)
    result = cursor.fetchone()

    if result == None:
        confirmation = False
    
    cursor.close()

    # true: user exists | false: user doesnt exist

    return confirmation

def check_userExistence_fromUserID(user_id):

    cursor = conn.cursor()

    confirmation = True

    QUERY = f"SELECT user_id FROM public.users WHERE user_id = '{user_id}'"

    logger.fromDatabase(QUERY)

    cursor.execute(QUERY)

    # fetch database for user_id (it should only be 1)
    result = cursor.fetchone()

    if result == None:
        confirmation = False
    
    cursor.close()

    # true: user exists | false: user doesnt exist

    return confirmation

def user_login(loginUser):

    email = loginUser.email
    password = loginUser.password

    cursor = conn.cursor()

    confirmation = False

    # first query, find password
    QUERY = f"SELECT user_id,password FROM public.users WHERE email = '{email}'" 

    logger.fromDatabase(QUERY)

    try:
        cursor.execute(QUERY)

        # fetch database for password (it should only be 1)
        result = cursor.fetchone()

        if result != None:
            hash = result[1] # position 0: id_user | position 1: password_hash
            if check_password_hash(password,hash):
                
                user_id = result[0]
                # second query, find api key
                QUERY = f"SELECT api_key FROM public.apiKeys WHERE user_id = '{user_id}'"

                logger.fromDatabase(QUERY)

                cursor.execute(QUERY)

                # fetch database for apikey (it should only be 1)
                result = cursor.fetchone()

                confirmation = result[0]

    except:

        logger.logDebug(str(traceback.format_exc()))
        return False

    cursor.close()

    # api-key: login approved | false: login failed

    return confirmation



def chat_type_fromChatID(chat_id):

    # db info:
    # chat: 2000000000000000000 
    # group: 3000000000000000000
    # channel: 4000000000000000000
    
    if chat_id[:1] == "2":
        return "chat"
    if chat_id[:1] == "3":
        return "group"
    if chat_id[:1] == "4":
        return "channel"
    return False


def has_user_access_to_chatID(sender,chat_id,type):

    if(type == "chat"):

        cursor = conn.cursor()

        # check if exist (from chat_id + sender)

        QUERY = f"SELECT chat_id FROM public.chats WHERE (chat_id = {chat_id} AND (user1 = {sender} OR user2 = {sender}))"

        logger.fromDatabase(QUERY)

        cursor.execute(QUERY)
        result = cursor.fetchone()

        if(result == None):
            
            logger.logDebug(f"{sender} has no access to {chat_id}")
            return False

        return str(result[0])


    if(type == "group"):

        return chat_id

    if(type == "channel"):

        return chat_id
        
    return False

def get_receiver_personalChat(chat_id,sender):

    cursor = conn.cursor()

    QUERY = f"SELECT user1,user2 FROM public.chats WHERE chat_id = {chat_id} AND (user1 = {sender} OR user2 = {sender})"

    logger.fromDatabase(QUERY)

    try:
        cursor.execute(QUERY)
        result = cursor.fetchone()

        if(str(result[0]) == sender):
            receiver = str(result[1])
        if(str(result[1]) == sender):
            receiver = str(result[0])

        cursor.close()

        return receiver
    
    except:
        logger.logDebug(str(traceback.format_exc()))  

    return None

def send_message(message):

    chat_id = message.chat_id
    text = message.text
    sender = message.sender # user_id
    date = message.date

    type = chat_type_fromChatID(chat_id) # Check what type of chat we need to send message

    logger.logDebug("Chat type: "+str(type))

    chat_id = has_user_access_to_chatID(sender,chat_id,type) # check if user has access to chat, if its exists and tries to create it

    if chat_id == False:  # Check if user can access chat messages
    
        # DA SISTEMARE
       return [False,"Error, cannot access chat",[]]


    receivers = []
    receivers.append(str(sender))

    if(type == "chat"):

        receivers.append(get_receiver_personalChat(chat_id,sender))

    if(type == "group"):

        # receiver array di persone
        return [False,"Not supported",[]]

    if(type == "channel"):

        return [False,"Not supported",[]]
    

    ## FIRST PHASE: ADD MESSAGE TO DB

    cursor = conn.cursor()

    QUERY = f"INSERT INTO public.messages (chat_id,text,sender,date) VALUES ({chat_id},'{text}',{sender},'{date}'); SELECT currval(pg_get_serial_sequence('public.messages','message_id'));" 

    logger.fromDatabase(QUERY)
    response_sender = False

    try:
        cursor.execute(QUERY)
        conn.commit()
        result = cursor.fetchone()
        message_id = str(result[0])

        # create response for messages sender (with message_id and date saved in local db on client)
        response_sender = {"type":"send_message","send_message": str(True),"date":str(date),"message_id":message_id,"chat_id":chat_id}

    except:
        logger.logDebug(str(traceback.format_exc()))
        conn.rollback()
        cursor.close()
        return [False,"Message_id not found",[]]
    
    cursor.close()

    ## SECOND PHASE: CREATE JSON MESSAGE FOR RESPONSE

    response_receiver = jsonBuilder.message_to_receiver(message_id,chat_id,text,sender,date)

    ## THIRD PHASE: RETURN ALL TO MAIN AND SENDS MESSAGES TO ALL 
    
    return [response_sender,response_receiver,receivers]

def get_chatID_personalChat(user1,user2):

    QUERY = f"SELECT chat_id FROM public.chats WHERE (user1 = {user1} AND user2 = {user2}) OR (user1 = {user2} AND user2 = {user1})"
    logger.fromDatabase(QUERY)

    cursor = conn.cursor()

    try:
        cursor.execute(QUERY)
        result = cursor.fetchone()
        cursor.close()

    except:
        logger.logDebug(str(traceback.format_exc()))
    
    if result == None:
        return False

    return result[0]
    
def create_personalChat(user1,user2):

    sender_response = {"type":"create_chat","create_chat":"True"}
    logger.logDebug("Creazione chat...")

    # check if both users exist
    if not (check_userExistence_fromUserID(user1) & check_userExistence_fromUserID(user2)):
        return False

    logger.logDebug("Utenti esistono!")
    
    # check if chat already exists

    chat_id = get_chatID_personalChat(user1,user2)
    if(chat_id!=False):
        return sender_response.update({"chat_id":chat_id})

    logger.logDebug("Chat non esiste!")
    
    # chat doesnt exists, we will then create it 

    ## ADD CHAT TO DB

    QUERY = f"INSERT INTO public.chats (user1,user2) VALUES ({user1},{user2}); SELECT currval(pg_get_serial_sequence('public.chats','chat_id'));" 
    logger.fromDatabase(QUERY)

    cursor = conn.cursor()
    try:
        cursor.execute(QUERY)
        conn.commit()
        result = cursor.fetchone()
        cursor.close()
    except:
        logger.logDebug(str(traceback.format_exc()))
        conn.rollback()
        return False # cannot create chat

    if result == None:
        return False

    return sender_response.update({"chat_id":result[0]})


def create_group(group):

    handle = group.handle       #admin + member of group
    name = group.name
    description = group.description

    # init members + admins arrays
    admins = members = [handle]
    
    cursor = conn.cursor()

    ## ADD GROUP TO DB


    #DA VERIFICARE IL FUNZIONAMENTO DI QUESTA QUERY ED EVENUTALMENTE IMPLEMENTARLA ANCHE PER PERSONAL CHAT CREATE ED ALTRI METODI CHE RICHIEDO LA CREAZIONE E IL RITIRO DELL'ID DELL' ELEMENTO CREATO
    QUERY = f"INSERT INTO public.groups (name,members,admins,description) VALUES ('{name}',{members},{admins}'{description}'); SELECT currval(pg_get_serial_sequence('public.groups','chat_id'));" 
    
    logger.fromDatabase(QUERY)

    try:
        cursor.execute(QUERY)
        conn.commit()
        result = cursor.fetchone()
    except:
        logger.logDebug(str(traceback.format_exc()))
        conn.rollback()
        return False # cannot create chat
    
    cursor.close()

    if result == None:
        return False

    return result[0] 

def upload_file(file):

    return None