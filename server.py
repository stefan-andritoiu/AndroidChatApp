#!/usr/bin/python3

import json
import sqlite3
import socket
import threading
import traceback

clients = []

class ChatDB:

    def __init__(self):
        self.conn = sqlite3.connect("chat.db")
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (id integer primary key, user text unique, password text)")
        c.execute("CREATE TABLE IF NOT EXISTS messages (id integer primary key, sender integer, receiver integer, message text, sent bool)")
        self.conn.commit()

    def add_user(self, user, password):
        c = self.conn.cursor()
        c.execute("INSERT INTO users (user, password) VALUES (?, ?)", (user, password))
        self.conn.commit()
        return self.check_user(user, password)

    def check_user(self, user, password):
        c = self.conn.cursor()
        c.execute("SELECT id FROM users where user = ? and password = ?", (user, password))
        result = c.fetchone()
        if result:
            return int(result[0])
        else:
            return None

    def exists_user(self, user):
        c = self.conn.cursor()
        c.execute("SELECT id FROM users WHERE user = ?", (user, ))
        result = c.fetchone()
        if result:
            return int(result[0])
        else:
            return None

    def add_message(self, sender, receiver, message, sent = False):
        if sent == True:
            sent = 1
        else:
            sent = 0
        c = self.conn.cursor()
        c.execute("INSERT INTO messages (sender, receiver, message, sent) VALUES (?, ?, ?, ?)", (sender, receiver, message, sent))
        self.conn.commit()

    def sent_message(self, messageid):
        c = self.conn.cursor()
        c.execute("UPDATE messages SET sent = 1 WHERE id = ?", (messageid, ))
        self.conn.commit()

    def unsent_messages(self, userid):
        c = self.conn.cursor()
        c.execute("SELECT messages.id, messages.message, users.user FROM messages JOIN users on messages.sender = users.id WHERE messages.receiver = ? AND messages.sent = 0", (userid, ))
        return c.fetchall()

    def get_users(self):
        c = self.conn.cursor()
        c.execute("SELECT user FROM users")
        return [row[0] for row in c.fetchall()]

class User(threading.Thread):
    def __init__(self, socket):
        self.socket = socket
        self.state = "Login"
        self.username = None
        self.userid = None
        threading.Thread.__init__(self)
        self.start()

    def login(self, json_message):
        user = ""
        password = ""
        #Check if login message  is correct
        if "user" in json_message and "pass" in json_message:
            user = json_message["user"]
            password = json_message["pass"]
        else:
            self.socket.send(json.dumps({"response": 1, "message": "Bad login message"}).encode("utf-8") + b'\0')
            raise Exception("Bad login")

        #Check if user needs to be created
        if "create" in json_message:
            create = json_message["create"]
        else:
            create = False

        #If user exists, login, otherwise create account
        if self.db.exists_user(user) and create == False:
            self.userid = self.db.check_user(user, password)
        elif create == True:
            self.userid = self.db.add_user(user, password)
        else:
            self.socket.send(json.dumps({"response": 3, "message": "Bad login message"}).encode("utf-8") + b'\0')
            raise Exception("Bad login")

        #Login failed
        if self.userid == None:
            self.socket.send(json.dumps({"response": 2, "message": "Unknown user"}).encode("utf-8") + b'\0')
            raise Exception("Unknown user")

        #If login succeeded, continue
        self.username = user
        users = self.db.get_users() + ["Echo", "EchoX2", "Echo5S"]
        self.socket.send(json.dumps({"response": 0, "message": "OK", "users": users}).encode("utf-8") + b'\0')
        print("User logged in:", self.username)
        self.state = "Authenticated"
        #Send pending messages
        messages = self.db.unsent_messages(self.userid)
        for message in messages:
            self.send_message(message[2], message[1])
            self.db.sent_message(message[0])

    def message(self, json_message):
        # Check if message is properly formatted
        if not ("users" in json_message and "message" in json_message):
            return
        for user in json_message["users"]:
            print("Sending to:", user)
            sent = False
            for client in clients:
                #Check if user is online
                #TODO: Use a hashtable
                if client.name() == user:
                    #If user online, try sending, otherwise mark message as not sent
                    #This might lead to missing messages, or messages sent multiple times
                    try:
                        client.send_message(self.name(), json_message["message"])
                        userid = client.id()
                        sent = True
                    except:
                        pass
            if not sent:
                userid = self.db.exists_user(user)
            #Add message to DB, clouds <3 your private conversations
            self.db.add_message(self.id(), userid, json_message["message"], sent)

    def parse_message(self, message):
        json_message = json.loads(message.decode("utf-8"))
        print(json_message)
        if self.state == "Login":
            self.login(json_message)
        else:
            self.message(json_message)

    def run(self):
        self.db = ChatDB()
        buf = b''
        running = True
        while running:
            aux_buf = self.socket.recv(4096)

            if len(aux_buf) == 0:
                buf += b'\0'
                running = False
                print("Client exiting...")
            else:
                buf += aux_buf

            messages = buf.split(b'\0', -1)
            if len(messages) > 1:
              buf = messages[-1]
              for message in messages[:-1]:
                  print(message)
                  if len(message) == 0:
                      continue
                  try:
                      self.parse_message(message)
                  except Exception as e:
                      print("Invalid message, kicking client:", e)
                      traceback.print_exc()
                      self.socket.close()
                      running = False
                      clients.remove(self)
                      break

    def name(self):
        return self.username

    def id(self):
        return self.userid

    def send_message(self, user, message, msg_type = 1):
        self.socket.send(json.dumps({"user": user, "message": message, "type": msg_type}).encode("utf-8") + b'\0')
        

class Echo(User):

    def __init__(self):
        User.__init__(self, None)

    def name(self):
        return "Echo"

    def run(self):
        print("Echo run")

    def id(self):
        return None

    def send_message(self, user, message):
        for client in clients:
            if client.name() == user:
                client.send_message("Echo", message)

class EchoX2(User):

    def __init__(self):
        User.__init__(self, None)

    def run(self):
        print("EchoX2 run")

    def name(self):
        return "EchoX2"

    def id(self):
        return None

    def send_message(self, user, message):
        for client in clients:
            if client.name() == user:
                client.send_message("EchoX2", message)
                client.send_message("EchoX2", message)

class EchoDelayed(User):

    def __init__(self):
        User.__init__(self, None)
 
    def run(self):
        print("EchoDelayed run")

    def name(self):
        return "EchoDelayed"

    def id(self):
        return None

    def send_message_delayed(self, user, message):
        for client in clients:
            if client.name() == user:
                client.send_message("EchoDelayed", message)

    def send_message(self, user, message, t = 5):
        threading.Timer(t, self.send_message_delayed, args = (user, message)).start()

def main():
    server = socket.socket()
    server.bind(("127.0.0.1", 4000))
    server.listen(10)
    print("Waiting for clients...")
    clients.append(Echo())
    clients.append(EchoX2())
    clients.append(EchoDelayed())
    while True:
        (client, address) = server.accept()
        print("Accepted client from: " + str(address))
        clients.append(User(client))
    
if __name__ == "__main__":
    main()