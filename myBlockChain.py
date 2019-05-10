import hashlib
import time
import csv
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import json
import re
from urllib.parse import parse_qs
from urllib.parse import urlparse
import threading
import cgi
import uuid
from tempfile import NamedTemporaryFile
import shutil
import requests # for sending new block to other nodes

PORT_NUMBER = 8099
g_txFileName = "txData.csv"  # 트랜잭션 저장하는 파일명
g_bcFileName = "blockchain.csv" #blockchian은 블록에 대한 정보를 담고있다.  블록 하나마다 트렌젝션이 포함 되어있다.
g_nodelstFileName = "nodelst.csv" # 인접 서버( ip) 와 port  노드들. 네트워킹 할 때 주소를 알아야하는데 그 주소 저장하는 파일
g_receiveNewBlock = "/node/receiveNewBlock" #url endpoint 서버가 떴을 때 전파되는 새로운 블록을 여기로 받겠다 -> 확인
g_difficulty = 2  ## 해시 값 앞에 숫자가  0 두개로 시작하면(00…) 인정하겠다.  난이도를 올리려면 숫자 up
g_maximumTry = 100 #최대 시도 횟수
g_nodeList = {'trustedServerAddress':'8099'} # trusted server list, should be checked manually


class Block:

    def __init__(self, index, previousHash, timestamp, data, currentHash, proof ): #여기서 self는 block클래스를 말함. 블록번호, 이전해시,현재블록생성시간,트랜젝션묶음,작업증명,현재해시
        self.index = index
        self.previousHash = previousHash
        self.timestamp = timestamp
        self.data = data
        self.currentHash = currentHash
        self.proof = proof

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4) #현재있는 데이터를 볼건데 딕셔너리형태로 클래스블록의 객체를 리턴. indent 탭을 기준으로 이쁘게 포맷팅해서 내보낸다.json.jump가 리턴하는 부분

class txData:

    def __init__(self, commitYN, sender, amount, receiver, uuid):
        self.commitYN = commitYN #0과 1로 기재한다. 채굴할 때 commitYN이 1이 아닌 데이터면 readTX를 호출한다.
        self.sender = sender
        self.amount = amount
        self.receiver = receiver
        self.uuid =  uuid

#여기부터 전역함수
def generateGenesisBlock(): #데이터를 처음 생성할 때 딱한번 호출되는 함수
    print("generateGenesisBlock is called")
    timestamp = time.time()
    print("time.time() => %f \n" % timestamp)
    tempHash = calculateHash(0, '0', timestamp, "Genesis Block", 0)
    print(tempHash)
    return Block(0, '0', timestamp, "Genesis Block",  tempHash,0)

def calculateHash(index, previousHash, timestamp, data, proof): #해시를 계산하는 함수
    value = str(index) + str(previousHash) + str(timestamp) + str(data) + str(proof)
    sha = hashlib.sha256(value.encode('utf-8'))
    return str(sha.hexdigest())  ## 16진수로 바꿔서 문자열로! tempHash로 리턴

def calculateHashForBlock(block): #블록번호, 생성시간, 거래데이터 등 계산한걸 256라인으로 해시한다.
    return calculateHash(block.index, block.previousHash, block.timestamp, block.data, block.proof)

def getLatestBlock(blockchain): #가장 최근블록을 리턴. 계산하기 위해서 위에있는 해시를 콜함.
    return blockchain[len(blockchain) - 1]

def generateNextBlock(blockchain, blockData, timestamp, proof): # 다음 블록을 생성해라 그럴려면 이전 해시값이 필요해서 가져온 것. 여기들어오는 blockdata는 트렌젝션데이터를 문자열로 길게 담은 것.
    previousBlock = getLatestBlock(blockchain) ## 현재 블록체인의 가장 최근블록
    nextIndex = int(previousBlock.index) + 1  ## 이전블록의 인덱스에 +1 한게 현재블록의 인덱스 값이기 때문에!
    nextTimestamp = timestamp
    nextHash = calculateHash(nextIndex, previousBlock.currentHash, nextTimestamp, blockData, proof) ## calculateHash 가 중요 //블록파라미터중 nexthash만 이함수 내에서 생성한 것 .
    # index, previousHash, timestamp, data, currentHash, proof
    return Block(nextIndex, previousBlock.currentHash, nextTimestamp, blockData, nextHash,proof) ## 리턴하면서 Block 객체 생성 nextHash 이거하나 구하려고. 여기서 블록객체가 하나 생성된거야

def writeBlockchain(blockchain):  ##블록체인이 채굴 되었을 때 csv파일로 써라.
    blockchainList = []  ## 리스트

    for block in blockchain:  ## block은 block객체임 block. 이면 객체의 변수가나옴 아래처럼 문자열로 튀어나옴 그걸 blockList에 넣음.
        blockList = [block.index, block.previousHash, str(block.timestamp), block.data, block.currentHash,block.proof ]
        blockchainList.append(blockList) ## blockchainList에 넣음 그럼 [[ block.index, block.previousHash, str(block.timestamp),. ....]] >> 2중리스트란 소리
        ## blockchainList 안에 이제 여러개?가 들어가는거임 [ [객체1][객체2] ] 이렇게..

    #[STARAT] check current db(csv) if broadcasted block data has already been updated
    lastBlock = None
    try:
        with open(g_bcFileName, 'r',  newline='') as file:  ## g_bcFileName 블록체인 파일을 염, 'r' 리드 모드로 염. ////with안에있는 생성된 결과를 as 뒤 변수에 넣겠다.  file은 오픈하고 , 'r'부분의 문장을 넣는다.
            blockReader = csv.reader(file)                  ## 기존블럭이 있을경우에만 들어옴 89~100 번째까지///while as 구문 안쓰면 파일 열 때 정상적이지 않으면 찌꺼기로 남는다. 안전장치 하는 거
            last_line_number = row_count(g_bcFileName)
            for line in blockReader:
                if blockReader.line_num == last_line_number:
                    lastBlock = Block(line[0], line[1], line[2], line[3], line[4], line[5])

        if int(lastBlock.index) + 1 != int(blockchainList[-1][0]):
            print("index sequence mismatch")
            if int(lastBlock.index) == int(blockchainList[-1][0]):
                print("db(csv) has already been updated")
            return
    except:
        print("file open error in check current db(csv) \n or maybe there's some other reason")
        pass
        #return
    # [END] check current db(csv)

    with open(g_bcFileName, "w", newline='') as file:  ## 여기서 이제 블록체인 파일을 write 함
        writer = csv.writer(file)
        writer.writerows(blockchainList)   ## 여러행을 writer 한다. 제너시스블록이 여기서 처음쓰여짐

    # update txData cause it has been mined.
    for block in blockchain:  ##
        updateTx(block)

    print('Blockchain written to blockchain.csv.')
    print('Broadcasting new block to other nodes')
    broadcastNewBlock(blockchain)  ## 인접한 서버들에 대해 내가 채굴했으니까 받아라!! 전파하는거임 네트웤상으로!

def readBlockchain(blockchainFilePath, mode = 'internal'): #78라인에서 csv로 쓴 블록체인정보를 불러온다.
    print("readBlockchain")
    importedBlockchain = [] #배열.

    try:
        with open(blockchainFilePath, 'r',  newline='') as file:
            blockReader = csv.reader(file) #csv파일을 꺼낸다. -128이동
            for line in blockReader:
                block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                importedBlockchain.append(block) #여기서 계속 붙는다.  블록이라는 클래스의 생성자를 호출하는 (csv reader)결과가 블록으로 들어온다. 블록은 객체고 importedblockchain은 리스트. 리스트안에 객체가 들어간다는 개념중요요
        print("Pulling blockchain from csv...")

        return importedBlockchain

    except:
        if mode == 'internal' : #내부에서 호출시 언제든 한번은 제네시스블록 생성해야한다. 아무것도 없기 때문에. 기본 internal.
            blockchain = generateGenesisBlock()
            importedBlockchain.append(blockchain) ## importedBlockchain 는 리스트 리스트안에 blockchain 객체가 들어온거 >>>>[ blockchain ] <<<<
            writeBlockchain(importedBlockchain)  ##
            return importedBlockchain
        else :
            return None

def updateTx(blockData) : #블록이 채굴 되었을 때 트렌젝션 데이터를 업데이트 한다. 채굴 되었을 때 호출되는 함수

    phrase = re.compile(r"\w+[-]\w+[-]\w+[-]\w+[-]\w+") # [6b3b3c1e-858d-4e3b-b012-8faac98b49a8]UserID hwang sent 333 bitTokens to UserID kim.
    matchList = phrase.findall(blockData.data)

    if len(matchList) == 0 :
        print ("No Match Found! " + str(blockData.data) + "block idx: " + str(blockData.index))
        return

    tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)

    with open(g_txFileName, 'r') as csvfile, tempfile:
        reader = csv.reader(csvfile)
        writer = csv.writer(tempfile)
        for row in reader:
            if row[4] in matchList:
                print('updating row : ', row[4])
                row[0] = 1
            writer.writerow(row)

    shutil.move(tempfile.name, g_txFileName)
    csvfile.close()
    tempfile.close()
    print('txData updated')

def writeTx(txRawData): # 거래내역을 csv파일로 기록. (거래는 했으나 아직 블록에는 포함되지 않았을 때)
    print(g_txFileName)
    txDataList = []
    for txDatum in txRawData:
        txList = [txDatum.commitYN, txDatum.sender, txDatum.amount, txDatum.receiver, txDatum.uuid]
        txDataList.append(txList)

    tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)
    try:
        with open(g_txFileName, 'r', newline='') as csvfile, tempfile:
            reader = csv.reader(csvfile)
            writer = csv.writer(tempfile)
            for row in reader:
                if row :
                    writer.writerow(row)
            # adding new tx
            writer.writerows(txDataList)
        shutil.move(tempfile.name, g_txFileName)
        csvfile.close()
        tempfile.close()
    except:
        # this is 1st time of creating txFile
        try:
            with open(g_txFileName, "w", newline='') as file:
                writer = csv.writer(file)
                writer.writerows(txDataList)
        except:
            return 0
    return 1
    print('txData written to txData.csv.')

def readTx(txFilePath): #트랜잭션데이터(거래내역)을 읽어들이겠다.
    print("readTx")
    importedTx = []

    try:
        with open(txFilePath, 'r',  newline='') as file:
            txReader = csv.reader(file)
            for row in txReader:
                if row[0] == '0': # find unmined txData
                    line = txData(row[0],row[1],row[2],row[3],row[4])
                    importedTx.append(line)
        print("Pulling txData from csv...")
        return importedTx
    except:
        return []

def getTxData(): #트렌젝션데이터를 읽어서 리턴할거다.
    strTxData = ''
    importedTx = readTx(g_txFileName)
    if len(importedTx) > 0 :
        for i in importedTx:
            print(i.__dict__) #인스턴스 멤버변수만 포함 이름고 값을 포함하는 사전출력
            transaction = "["+ i.uuid + "]" "UserID " + i.sender + " sent " + i.amount + " bitTokens to UserID " + i.receiver + ". " #
            print(transaction)
            strTxData += transaction

    return strTxData

def mineNewBlock(difficulty=g_difficulty, blockchainPath=g_bcFileName):  ## g_difficulty 는 난이도
    blockchain = readBlockchain(blockchainPath)
    strTxData = getTxData() ## 트랜잭션 데이타를 읽어와라 문자열임
    if strTxData == '' :  ## 널값이면 잘못된거임
        print('No TxData Found. Mining aborted')
        return

    timestamp = time.time() ## 현재블록의 첫 생성시도 시각
    proof = 0  ## 작업증명횟수는 0으로 초기화
    newBlockFound = False  ## while 문 탈출조건

    print('Mining a block...')

    while not newBlockFound: ## 처음에 newBlockFound가 false 니까 true라 계속 도는 조건임
        newBlockAttempt = generateNextBlock(blockchain, strTxData, timestamp, proof) ## generateNextBlock 가 블록을 만드는거 ! 시도해보는것,
        if newBlockAttempt.currentHash[0:difficulty] == '0' * difficulty:  ## 난이도를 만족한다면 나와서 writeblockchain 를 호출한다.
            stopTime = time.time()  ## 의미없고 몇초걸리는지 궁금해서 넣음 여기부터 아래 2줄까지
            timer = stopTime - timestamp
            print('New block found with proof', proof, 'in', round(timer, 2), 'seconds.')
            newBlockFound = True  ## if문의 현재블록의시도값이 0부터 difficulty(2) 까지
        else:
            proof += 1  ## 만족하지 않을 경우 proof(작업증명횟수)만 올리고 다시 올라간다. while난이도 조건에 맞을 때 까지 계속돈다. 여기가 main.

    blockchain.append(newBlockAttempt) ## 리스트에 지금채굴한 블럭을 더함
    writeBlockchain(blockchain) ## 그걸 writeBlockchain 함

def mine():
    mineNewBlock()

def isSameBlock(block1, block2): #64라인에서 보낸 정보를 여기로 가져온다.
    if str(block1.index) != str(block2.index):
        return False
    elif str(block1.previousHash) != str(block2.previousHash):
        return False
    elif str(block1.timestamp) != str(block2.timestamp):
        return False
    elif str(block1.data) != str(block2.data):
        return False
    elif str(block1.currentHash) != str(block2.currentHash):
        return False
    elif str(block1.proof) != str(block2.proof):
        return False
    return True

def isValidNewBlock(newBlock, previousBlock): #블록체인 검증. 외부에서 받은 블록체인 데이터를 내블록체인데이터와 비교
    if int(previousBlock.index) + 1 != int(newBlock.index):
        print('Indices Do Not Match Up')
        return False
    elif previousBlock.currentHash != newBlock.previousHash:
        print("Previous hash does not match")
        return False
    elif calculateHashForBlock(newBlock) != newBlock.currentHash:
        print("Hash is invalid")
        return False
    elif newBlock.currentHash[0:g_difficulty] != '0' * g_difficulty:
        print("Hash difficulty is invalid")
        return False
    return True

def newtx(txToMining): #새로운 거래데이터 즉 트렌젝션이 들어왔을 때 연결해주는 함수 --> 확인

    newtxData = []
    # transform given data to txData object
    for line in txToMining:
        tx = txData(0, line['sender'], line['amount'], line['receiver'], uuid.uuid4())
        newtxData.append(tx)

    # limitation check : max 5 tx
    if len(newtxData) > 5 : #쌍이 5개 이상이면 안받아. 교수님이 설정하신거 무의미라고 하심
        print('number of requested tx exceeds limitation')
        return -1

    if writeTx(newtxData) == 0:
        print("file write error on txData")
        return -2
    return 1

def isValidChain(bcToValidate): #블록체인이 유효한지 검증.
    genesisBlock = []
    bcToValidateForBlock = []

    # Read GenesisBlock
    try:
        with open(g_bcFileName, 'r',  newline='') as file:
            blockReader = csv.reader(file)
            for line in blockReader:
                block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                genesisBlock.append(block)
#                break
    except:
        print("file open error in isValidChain")
        return False

    # transform given data to Block object
    for line in bcToValidate:
        # print(type(line))
        # index, previousHash, timestamp, data, currentHash, proof
        block = Block(line['index'], line['previousHash'], line['timestamp'], line['data'], line['currentHash'], line['proof'])
        bcToValidateForBlock.append(block)

    #if it fails to read block data  from db(csv)
    if not genesisBlock:
        print("fail to read genesisBlock")
        return False

    # compare the given data with genesisBlock
    if not isSameBlock(bcToValidateForBlock[0], genesisBlock[0]):
        print('Genesis Block Incorrect')
        return False

    #tempBlocks = [bcToValidateForBlock[0]]
    #for i in range(1, len(bcToValidateForBlock)):
    #    if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
    #        tempBlocks.append(bcToValidateForBlock[i])
    #    else:
    #        return False

    for i in range(0, len(bcToValidateForBlock)):
        if isSameBlock(genesisBlock[i], bcToValidateForBlock[i]) == False:
            return False

    return True

def addNode(queryStr): #인접 노드에 새로운것 추가하겠다 ---> 확인 인접 서버에 대한 정보를 등록하는 함수
    # save
    txDataList = []
    txDataList.append([queryStr[0],queryStr[1],0]) # ip, port, # of connection fail

    tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)
    try:
        with open(g_nodelstFileName, 'r', newline='') as csvfile, tempfile:
            reader = csv.reader(csvfile)
            writer = csv.writer(tempfile)
            for row in reader:
                if row:
                    if row[0] == queryStr[0] and row[1] == queryStr[1]:
                        print("requested node is already exists")
                        csvfile.close()
                        tempfile.close()
                        return -1
                    else:
                        writer.writerow(row)
            writer.writerows(txDataList)
        shutil.move(tempfile.name, g_nodelstFileName)
        csvfile.close()
        tempfile.close()
    except:
        # this is 1st time of creating node list
        try:
            with open(g_nodelstFileName, "w", newline='') as file:
                writer = csv.writer(file)
                writer.writerows(txDataList)
        except:
            return 0
    return 1
    print('new node written to nodelist.csv.')

def readNodes(filePath): # 인접서버에 대한 정보를 350에 등록해서 내가 알고있잖아 그걸 읽어서 적용
    print("read Nodes")
    importedNodes = []

    try:
        with open(filePath, 'r',  newline='') as file:
            txReader = csv.reader(file)
            for row in txReader:
                line = [row[0],row[1]]
                importedNodes.append(line)
        print("Pulling txData from csv...")
        return importedNodes
    except:
        return []

def broadcastNewBlock(blockchain): #내가 가지고 있는 인접서버 노드들에 내가 채굴했던 블록을 만들어 전파하는 것.
    #newBlock  = getLatestBlock(blockchain) # get the latest block
    importedNodes = readNodes(g_nodelstFileName) # get server node ip and port
    reqHeader = {'Content-Type': 'application/json; charset=utf-8'}
    reqBody = []
    for i in blockchain:
        reqBody.append(i.__dict__)

    if len(importedNodes) > 0 :
        for node in importedNodes:
            try:
                URL = "http://" + node[0] + ":" + node[1] + g_receiveNewBlock  # http://ip:port/node/receiveNewBlock
                res = requests.post(URL, headers=reqHeader, data=json.dumps(reqBody))
                if res.status_code == 200:
                    print(URL + " sent ok.")
                    print("Response Message " + res.text)
                else:
                    print(URL + " responding error " + res.status_code)
            except:
                print(URL + " is not responding.")
                # write responding results
                tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)
                try:
                    with open(g_nodelstFileName, 'r', newline='') as csvfile, tempfile:
                        reader = csv.reader(csvfile)
                        writer = csv.writer(tempfile)
                        for row in reader:
                            if row:
                                if row[0] == node[0] and row[1] ==node[1]:
                                    print("connection failed "+row[0]+":"+row[1]+", number of fail "+row[2])
                                    tmp = row[2]
                                    # too much fail, delete node
                                    if int(tmp) > g_maximumTry:
                                        print(row[0]+":"+row[1]+" deleted from node list because of exceeding the request limit")
                                    else:
                                        row[2] = int(tmp) + 1
                                        writer.writerow(row)
                                else:
                                    writer.writerow(row)
                    shutil.move(tempfile.name, g_nodelstFileName)
                    csvfile.close()
                    tempfile.close()
                except:
                    print("caught exception while updating node list")

def row_count(filename):
    try:
        with open(filename) as in_file:
            return sum(1 for _ in in_file)
    except:
        return 0

def compareMerge(bcDict): #여기부터 외부블록과 내블록 비교시작

    heldBlock = []
    bcToValidateForBlock = []

    # Read GenesisBlock
    try:
        with open(g_bcFileName, 'r',  newline='') as file:
            blockReader = csv.reader(file)
            #last_line_number = row_count(g_bcFileName)
            for line in blockReader:
                block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                heldBlock.append(block)
                #if blockReader.line_num == 1:
                #    block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                #    heldBlock.append(block)
                #elif blockReader.line_num == last_line_number:
                #    block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                #    heldBlock.append(block)

    except:
        print("file open error in compareMerge or No database exists")
        print("call initSvr if this server has just installed")
        return -1

    #if it fails to read block data  from db(csv)
    if len(heldBlock) == 0 :
        print("fail to read")
        return -2

    # transform given data to Block object
    for line in bcDict:
        # print(type(line))
        # index, previousHash, timestamp, data, currentHash, proof
        block = Block(line['index'], line['previousHash'], line['timestamp'], line['data'], line['currentHash'], line['proof'])
        bcToValidateForBlock.append(block)

    # compare the given data with genesisBlock
    if not isSameBlock(bcToValidateForBlock[0], heldBlock[0]):
        print('Genesis Block Incorrect')
        return -1

    # check if broadcasted new block,1 ahead than > last held block

    if isValidNewBlock(bcToValidateForBlock[-1],heldBlock[-1]) == False:

        # latest block == broadcasted last block
        if isSameBlock(heldBlock[-1], bcToValidateForBlock[-1]) == True:
            print('latest block == broadcasted last block, already updated')
            return 2
        # select longest chain
        elif len(bcToValidateForBlock) > len(heldBlock):
            # validation
            if isSameBlock(heldBlock[0],bcToValidateForBlock[0]) == False:
                    print("Block Information Incorrect #1")
                    return -1
            tempBlocks = [bcToValidateForBlock[0]]
            for i in range(1, len(bcToValidateForBlock)):
                if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
                    tempBlocks.append(bcToValidateForBlock[i])
                else:
                    return -1
            # [START] save it to csv
            blockchainList = []
            for block in bcToValidateForBlock:
                blockList = [block.index, block.previousHash, str(block.timestamp), block.data,
                             block.currentHash, block.proof]
                blockchainList.append(blockList)
            with open(g_bcFileName, "w", newline='') as file:
                writer = csv.writer(file)
                writer.writerows(blockchainList)
            # [END] save it to csv
            return 1
        elif len(bcToValidateForBlock) < len(heldBlock):
            # validation
            #for i in range(0,len(bcToValidateForBlock)):
            #    if isSameBlock(heldBlock[i], bcToValidateForBlock[i]) == False:
            #        print("Block Information Incorrect #1")
            #        return -1
            tempBlocks = [bcToValidateForBlock[0]]
            for i in range(1, len(bcToValidateForBlock)):
                if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
                    tempBlocks.append(bcToValidateForBlock[i])
                else:
                    return -1
            print("We have a longer chain")
            return 3
        else:
            print("Block Information Incorrect #2")
            return -1
    else: # very normal case (ex> we have index 100 and receive index 101 ...)
        tempBlocks = [bcToValidateForBlock[0]]
        for i in range(1, len(bcToValidateForBlock)):
            if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
                tempBlocks.append(bcToValidateForBlock[i])
            else:
                print("Block Information Incorrect #2 "+tempBlocks.__dict__)
                return -1

        print("new block good")

        # validation
        for i in range(0, len(heldBlock)):
            if isSameBlock(heldBlock[i], bcToValidateForBlock[i]) == False:
                print("Block Information Incorrect #1")
                return -1
        # [START] save it to csv
        blockchainList = []
        for block in bcToValidateForBlock:
            blockList = [block.index, block.previousHash, str(block.timestamp), block.data, block.currentHash, block.proof]
            blockchainList.append(blockList)
        with open(g_bcFileName, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerows(blockchainList)
        # [END] save it to csv
        return 1

def initSvr(): #서버를 처음 띄울 때 처음 부르는 함수. 내가 모르고 있는 인접노드의 정보라면 인접노드를 확인해서 알려달라고 하는거야. 만약 내가 알고있으면 넘어간다.
    print("init Server") #즉 아는 서버가서 그 블록체인 정보 좀 달라고 하는것
    # 1. check if we have a node list file
    last_line_number = row_count(g_nodelstFileName)
    # if we don't have, let's request node list
    if last_line_number == 0:
        # get nodes...
        for key, value in g_nodeList.items():
            URL = 'http://'+key+':'+value+'/node/getNode'
            try:
                res = requests.get(URL)
            except requests.exceptions.ConnectionError:
                continue
            if res.status_code == 200 :
                print(res.text)
                tmpNodeLists = json.loads(res.text)
                for node in tmpNodeLists:
                    addNode(node)

    # 2. check if we have a blockchain data file
    last_line_number = row_count(g_bcFileName)
    blockchainList=[]
    if last_line_number == 0:
        # get Block Data...
        for key, value in g_nodeList.items():
            URL = 'http://'+key+':'+value+'/block/getBlockData'
            try:
                res = requests.get(URL)
            except requests.exceptions.ConnectionError:
                continue
            if res.status_code == 200 :
                print(res.text)
                tmpbcData = json.loads(res.text)
                for line in tmpbcData:
                    # print(type(line))
                    # index, previousHash, timestamp, data, currentHash, proof
                    block = [line['index'], line['previousHash'], line['timestamp'], line['data'],line['currentHash'], line['proof']]
                    blockchainList.append(block)
                try:
                    with open(g_bcFileName, "w", newline='') as file:
                        writer = csv.writer(file)
                        writer.writerows(blockchainList)
                except Exception as e:
                    print("file write error in initSvr() "+e)

    return 1

# This class will handle any incoming request from
# a browser
class myHandler(BaseHTTPRequestHandler):

    #def __init__(self, request, client_address, server):
    #    BaseHTTPRequestHandler.__init__(self, request, client_address, server)

    # Handler for the GET requests
    def do_GET(self): #여기가 시작점
        data = []  # response json data
        if None != re.search('/block/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            if None != re.search('/block/getBlockData', self.path):  ## 이렇게 getBlockData를 한번에 주면 안됨, getBlockData가 엄청크면 서버죽음 ㅠㅠ doget부터 1. 여기까지 블록데이터 주세요 하는것
                                                                     ## 페이징처리를 해야함  범위처리가 빠졌다 코드에는
                # TODO: range return (~/block/getBlockData?from=1&to=300)
                # queryString = urlparse(self.path).query.split('&')

                block = readBlockchain(g_bcFileName, mode = 'external') #2. 그럼 읽어서 리턴해주면 되지

                if block == None :
                    print("No Block Exists")

                    data.append("no data exists")
                else :
                    for i in block:
                        print(i.__dict__)
                        data.append(i.__dict__)

                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))

            elif None != re.search('/block/generateBlock', self.path): # 블록체인을 채굴해주세요 하는 요청. 외부에서 요청이 들어왔을 때
                t = threading.Thread(target=mine)
                t.start()
                data.append("{mining is underway:check later by calling /block/getBlockData}")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))#여기서 블록체인.csv생겨
            else:
                data.append("{info:no such api}")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))
        elif None != re.search('/node/*', self.path):  ## 처음호출될때 아무것도없으니 이놈이 호출됨
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            if None != re.search('/node/addNode', self.path): #서버를 추가할게요? 서버정보를 주세요? ---- 확인
                queryStr = urlparse(self.path).query.split(':') #블록의 path찍으니까 당연히 127.0.0.1로 고정이지 그럼 같은 ip,포트로 보내보면 node.csv가 생기네에
                print (self.client_address)
                print("client ip : "+self.client_address[0]+" query ip : "+queryStr[0])
                if self.client_address[0] != queryStr[0]:
                    data.append("your ip address doesn't match with the requested parameter")#(676이동)
                else:
                    res = addNode(queryStr)
                    if res == 1:
                        importedNodes = readNodes(g_nodelstFileName)
                        data =importedNodes
                        print("node added okay")
                    elif res == 0 :
                        data.append("caught exception while saving")
                    elif res == -1 :
                        importedNodes = readNodes(g_nodelstFileName)
                        data = importedNodes
                        data.append("requested node is already exists")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))
            elif None != re.search('/node/getNode', self.path):
                importedNodes = readNodes(g_nodelstFileName)
                data = importedNodes
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))
        else:
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
        # ref : https://mafayyaz.wordpress.com/2013/02/08/writing-simple-http-server-in-python-with-rest-and-json/

    def do_POST(self): #포스트맨에서 newtx보내면 여기서 받아서 710으로 이동

        if None != re.search('/block/*', self.path): #외부에서 포스트 방식으로 블록정보 붙혀서 나한테 호출해줬어 -695이동
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            if None != re.search('/block/validateBlock/*', self.path): #그럼 내가 가진 블록정보랑 비교해서 보내준다.
                ctype, pdict = cgi.parse_header(self.headers['content-type'])
                #print(ctype) #print(pdict)

                if ctype == 'application/json':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    receivedData = post_data.decode('utf-8')
                    print(type(receivedData))
                    tempDict = json.loads(receivedData)  # load your str into a list #print(type(tempDict))
                    if isValidChain(tempDict) == True :
                        tempDict.append("validationResult:normal")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    else :
                        tempDict.append("validationResult:abnormal")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
            elif None != re.search('/block/newtx', self.path): #새로운 블록이 들어오면 트렌젝션에 등록한다. 여기로 들어오면 717이동
                ctype, pdict = cgi.parse_header(self.headers['content-type'])
                if ctype == 'application/json':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    receivedData = post_data.decode('utf-8')
                    print(type(receivedData))
                    tempDict = json.loads(receivedData) #여기서 제이슨으로 다 변환하고 tempdict에 넣어서 다시 호출해
                    res = newtx(tempDict)
                    if  res == 1 :
                        tempDict.append("accepted : it will be mined later")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    elif res == -1 :
                        tempDict.append("declined : number of request txData exceeds limitation")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    elif res == -2 :
                        tempDict.append("declined : error on data read or write")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    else :
                        tempDict.append("error : requested data is abnormal")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))

        elif None != re.search('/node/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            if None != re.search(g_receiveNewBlock, self.path): # /node/receiveNewBlock 다른서버가 브로드캐스트던졌을 때 내 블록에 추가한다 ??????
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                receivedData = post_data.decode('utf-8')
                tempDict = json.loads(receivedData)  # load your str into a list
                print(tempDict)
                res = compareMerge(tempDict)
                if res == -1: # internal error
                    tempDict.append("internal server error")
                elif res == -2 : # block chain info incorrect
                    tempDict.append("block chain info incorrect")
                elif res == 1: #normal
                    tempDict.append("accepted")
                elif res == 2: # identical
                    tempDict.append("already updated")
                elif res == 3: # we have a longer chain
                    tempDict.append("we have a longer chain")
                self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

        return

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

try:

    # Create a web server and define the handler to manage the
    # incoming request
    # server = HTTPServer(('', PORT_NUMBER), myHandler)
    server = ThreadedHTTPServer(('', PORT_NUMBER), myHandler) #thread처리. 동시처리 가능하다.
    print('Started httpserver on port ', PORT_NUMBER)

    initSvr()
    # Wait forever for incoming http requests
    server.serve_forever()

except (KeyboardInterrupt, Exception) as e:
    print('^C received, shutting down the web server')
    print(e)
    server.socket.close()