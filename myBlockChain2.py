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
g_txFileName = "txData.csv"
g_bcFileName = "blockchain.csv"
g_nodelstFileName = "nodelst.csv"
g_receiveNewBlock = "/node/receiveNewBlock"
g_difficulty = 2
g_maximumTry = 100
g_nodeList = {'trustedServerAddress':'8099'} # trusted server list, should be checked manually


class Block:

    def __init__(self, index, previousHash, timestamp, data, currentHash, proof ):
        self.index = index
        self.previousHash = previousHash
        self.timestamp = timestamp
        self.data = data
        self.currentHash = currentHash
        self.proof = proof

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)

class txData:

    def __init__(self, commitYN, sender, amount, receiver, uuid):
        self.commitYN = commitYN
        self.sender = sender
        self.amount = amount
        self.receiver = receiver
        self.uuid =  uuid

#block과 hash를 생성해서 block객체에 담아서 리턴한다
def generateGenesisBlock():
    print("generateGenesisBlock is called")

    #teimestamp는 1970년 1월1일 자정 이후로 초단위로 츠겆ㅇ한 절대시간을 의미하는 단순변수이며,
    #이 변수에 time.time()으로 위에서부터 누적된 초를 float자료형으로 반환하여 대입한다.
    timestamp = time.time()
    #불러온 시간 확인
    print("time.time() => %f \n" % timestamp)
    #hash생성

    tempHash = calculateHash(0, '0', timestamp, "Genesis Block", 0)
    print(tempHash)
    # 생성된 문자열 형태의 hash값을 생성자로 생성된 block객체에 담아 리턴한다.
    # 이때, 블록인덱스, 이전hash값, 생성시간, 블록의 종류, 현재hash값, 검증 의 값들 또한 대입하여 리턴한다.
    # 주의해야 할 점은, 최초의 블록생성이므로 블록인덱스 = 0 이고, 이전 문자열자료형인 hash값은 '0'이 된다.
    return Block(0, '0', timestamp, "Genesis Block",  tempHash,0)

#입력받은 인자들을 str자료형으로 캐스팅하고 한 문장으로 value에 저장하여 value를 기반으로 해쉬값을 만든다.
def calculateHash(index, previousHash, timestamp, data, proof):
    value = str(index) + str(previousHash) + str(timestamp) + str(data) + str(proof)
    #인자로 받은 모든 데이터를 차례대로 더한 value 문자열을 utf-8로 인코딩한후 hashlib.sha256를 통해 해쉬암호화한다
    #sha256은 암호학적 해쉬함수의 한 종류. utf-8로 인코딩을 하지않고 쓰면 에러난다. 반환값은 hash객체.hash자료형 아니다. 객체다
    sha = hashlib.sha256(value.encode('utf-8'))
    #hash객체에서 제공하는 hexdigest() 메소드는 오직 16진수숫자만 포함하는 이중길이(?)의 해쉬값을 문자열로 변환하여 반환한다.
    return str(sha.hexdigest())

def calculateHashForBlock(block):
    return calculateHash(block.index, block.previousHash, block.timestamp, block.data, block.proof)

def getLatestBlock(blockchain):
    return blockchain[len(blockchain) - 1]

def generateNextBlock(blockchain, blockData, timestamp, proof):
    previousBlock = getLatestBlock(blockchain)
    nextIndex = int(previousBlock.index) + 1
    nextTimestamp = timestamp
    nextHash = calculateHash(nextIndex, previousBlock.currentHash, nextTimestamp, blockData, proof)
    # index, previousHash, timestamp, data, currentHash, proof
    return Block(nextIndex, previousBlock.currentHash, nextTimestamp, blockData, nextHash,proof)

#parameter또한 block객체list이다.
def writeBlockchain(blockchain):
    #list
    blockchainList = []

    #blockchain의 block객체들을 순차적으로 해체 하여 blockList에 담는다. 이때 blockList는 list 자료형이며,
    #blockchainList은 이러한 list들의 list이다. 즉 list자료형변수들의 list.
    #block객체list들의 block자료형 객체들의 변수들을 list형 변수에 차례로 담고, 그 list형 변수들을 차례로 list자료형 list에 담는 과정임.
    #이러한 귀찮은 과정을 거치는 이유는 blockchain.csv파일에 block의 내용을 문자열 형태로 하나하나 저장해주기 위해 이 과정을 거치는 거임.
    for block in blockchain:
        blockList = [block.index, block.previousHash, str(block.timestamp), block.data, block.currentHash,block.proof ]
        blockchainList.append(blockList)

    #[STARAT] check current db(csv) if broadcasted block data has already been updated
    lastBlock = None
    try:
        #'bloackchain.csv'파일을 'r'(읽기)모드로 file의 별칭을 주어 스트림을 연다. 여기서 csv파일이 존재하지않으면 except로 빠진다.
        #최초로 block를 생성할때는, csv파일이 존재하지 않으므로 except로 빠진다.
        with open(g_bcFileName, 'r',  newline='') as file:
            blockReader = csv.reader(file)
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
        #pass는 실행 할 것이 아무 것도 없다는 것을 의미. 따라서 아무런 동작을 하지 않고 다음 코드를 실행.
        #except바깥의 아래 코드로 이동한다.
        pass
        #return
    # [END] check current db(csv)

    # 'bloackchain.csv'파일을 'w'(쓰기)모드로 file의 별칭을 주어 스트림을 연다.
    # 'w'(쓰기)모드의 경우, 파일이 존재하면 원래 있던 내용이 모두 사라지고, 파일이 존재하지 않는 경우 새로운 파일이 생성된다.
    # 즉, 최초의 블록, genesis block이 생성되는 경우 blockchain.csv 파일은 이 곳에서 최초로 생성이 되는 것임.
    # 또한, as file : 의 : 를 꼭 기억하자. 아마도 파일스트림을 열고 해야할 작업을 마치면 자동으로 닫히게 되는 구조인가 보다.
    with open(g_bcFileName, "w", newline='') as file:
        # 이곳에서 최초로 생성한 blockchain.csv에 block객체의 내용을 순차적으로 담은 list변수를 담은 list변수의 list인 blockchainList에서
        # list변수들을 차례대로 해당 변수의 내용들을 csv파일에 '라인단위'로 저장해준다. 그것을 해주는 메소드가 writerows이다.
        # writerow(리스트)는 하나의 리스트변수만 해주고, writerows(리스트)는 리스트 안에 존재하는 모든 list형 변수를 차례로 저장해준다.
        # 참고사이트 : http://zetcode.com/python/csv/ =>근데 영어임 ㅠㅠ. 그래도 이해하기 쉬움
        writer = csv.writer(file)
        writer.writerows(blockchainList)

    # update txData cause it has been mined.
    # block이 최초로 생성되는 경우, 거래내역 자체가 없으므로 걍 패스
    for block in blockchain:
        updateTx(block)

    print('Blockchain written to blockchain.csv.')
    print('Broadcasting new block to other nodes')
    #block가 생성이 되었으므로 모든 node들에게 생성되었음을 알린다.
    broadcastNewBlock(blockchain)

#mode의 초기값은 internal이므로, mode가 명시되어있지 않는 경우, blockchain.csv파일이 존재하지 않을 때, except로 빠져
# internal에 해당하는 if문이 실행된다.
def readBlockchain(blockchainFilePath, mode = 'internal'):
    print("readBlockchain")
    importedBlockchain = []

    try:
        #blockchainFilePath = 'blcokchain.csv' 즉, 해당 파일을 'r' 읽기 형태로 file이라는 별칭(객체)으로 연다.
        with open(blockchainFilePath, 'r',  newline='') as file:
            #csv.reader(별칭)이 성공하면 reader객체를 리턴한다.
            blockReader = csv.reader(file)
            # file의 한 라인씩을 가져온다.
            for line in blockReader:
                block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                importedBlockchain.append(block)

        print("Pulling blockchain from csv...")

        return importedBlockchain

    #가장 맨처음에 데이터확인url을 날리는 경우,  'blockchain.csv' 파일이 존재하지 않으므로 csv.reader에서 예외처리로 넘어오게된다.
    except:
        #현재 모드가 internal(내부)이라면, 새로운 블록을 생성한다.
        if mode == 'internal' :

            blockchain = generateGenesisBlock()
            #생성된 블록을 importedBlockchain의 block객체list에 넣는다.
            importedBlockchain.append(blockchain)
            #block객체list를 인자로 던진다.
            writeBlockchain(importedBlockchain)
            return importedBlockchain
        #현재 모드가 external(외부)이라면,
        else :
            #None 리턴
            return None

#block객체의
def updateTx(blockData) :
    
    #정규표현식 설정
    phrase = re.compile(r"\w+[-]\w+[-]\w+[-]\w+[-]\w+") # [6b3b3c1e-858d-4e3b-b012-8faac98b49a8]UserID hwang sent 333 bitTokens to UserID kim.
    # block객체의 data field에서 해당 정규표현식과 매칭되는 부분을 전부 찾는다. data는 string 변수.
    # 주의할 점은, block 최초로 생성되었 때의 block인 genesis Block의 data는 "genesis Block"이므로, matchList는 결과적으로 아무것도 들어있지 않는
    # 상태이다. 다만, block이 최초로 생성되는 상황에서는 거래가 있을수가 없기 때문인지, 아니면 genesis Block은 그자체로 거래불가인지는 모르겠음.
    matchList = phrase.findall(blockData.data)

    #해당 block객체가 거래내역(data)이 없는 경우
    if len(matchList) == 0 :
        print ("No Match Found! " + str(blockData.data) + "block idx: " + str(blockData.index))
        #block의 data field 에서 거래내역을 찾지 못했으므로 바로 리턴
        return

    # data 내에 정규표현식에 해당하는 문자열, 즉 거래내역이 존재하는 경우, 임시로 파일 스트림을 연다.
    # 임시로 여는 파일은 scope안에서면 사용되고 사라진다.
    # 왜 임시로 열었는지는 의문. 왜 임시로 열고 저장은 하는지는 의문. 왜 임시로 열었는데 delete = false인지는 의문
    # 참고사이트 : https://medium.com/@silmari/python-tempfile-%EC%9E%84%EC%8B%9C%ED%8C%8C%EC%9D%BC-%EB%B0%8F-%ED%8F%B4%EB%8D%94-%EB%A7%8C%EB%93%A4%EA%B8%B0-86ea533086ce
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

def writeTx(txRawData):
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

def readTx(txFilePath):
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

def getTxData():
    strTxData = ''
    importedTx = readTx(g_txFileName)
    if len(importedTx) > 0 :
        for i in importedTx:
            print(i.__dict__)
            transaction = "["+ i.uuid + "]" "UserID " + i.sender + " sent " + i.amount + " bitTokens to UserID " + i.receiver + ". " #
            print(transaction)
            strTxData += transaction

    return strTxData

#새로운 블록을 생성해내는 함수. difficulty = 2(채굴 난이도), blockchainPath = blockchain.csv. 채굴과 동시에 excel에 기록된다
def mineNewBlock(difficulty=g_difficulty, blockchainPath=g_bcFileName):
    #
    blockchain = readBlockchain(blockchainPath)
    strTxData = getTxData()
    if strTxData == '' :
        print('No TxData Found. Mining aborted')
        return

    timestamp = time.time()
    proof = 0
    newBlockFound = False

    print('Mining a block...')

    while not newBlockFound:
        newBlockAttempt = generateNextBlock(blockchain, strTxData, timestamp, proof)
        if newBlockAttempt.currentHash[0:difficulty] == '0' * difficulty:
            stopTime = time.time()
            timer = stopTime - timestamp
            print('New block found with proof', proof, 'in', round(timer, 2), 'seconds.')
            newBlockFound = True
        else:
            proof += 1

    blockchain.append(newBlockAttempt)
    writeBlockchain(blockchain)

#mineNewBlock() : 235
def mine():
    mineNewBlock()

def isSameBlock(block1, block2):
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

#외부에서 받은 블록들을 비교한다(순서 6개의 경우: [1,2], [2,3] ... [5,6]
def isValidNewBlock(newBlock, previousBlock):
    if int(previousBlock.index) + 1 != int(newBlock.index):
        print('Indices Do Not Match Up')
        return False
    #체이닝이 맞는지
    elif previousBlock.currentHash != newBlock.previousHash:
        print("Previous hash does not match")
        return False
    #해쉬검증
    elif calculateHashForBlock(newBlock) != newBlock.currentHash:
        print("Hash is invalid")
        return False
    elif newBlock.currentHash[0:g_difficulty] != '0' * g_difficulty:
        print("Hash difficulty is invalid")
        return False
    return True

def newtx(txToMining):

    newtxData = []
    # transform given data to txData object
    for line in txToMining:
        tx = txData(0, line['sender'], line['amount'], line['receiver'], uuid.uuid4())
        newtxData.append(tx)

    # limitation check : max 5 tx
    if len(newtxData) > 5 :
        print('number of requested tx exceeds limitation')
        return -1

    if writeTx(newtxData) == 0:
        print("file write error on txData")
        return -2
    return 1

def isValidChain(bcToValidate):
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

def addNode(queryStr):
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
#g_nodelstFileName, "nodelst.csv"의 내용을 읽어온다.
def readNodes(filePath):
    print("read Nodes")
    importedNodes = []

    try:
        #"nodelist.csv"를 읽기모드로 file 별칭을 주어 파일스트림을 연다. 해당 파일이 존재하지 않는 경우는 except로 빠진다.
        with open(filePath, 'r',  newline='') as file:
            txReader = csv.reader(file)
            for row in txReader:
                line = [row[0],row[1]]
                importedNodes.append(line)
        print("Pulling txData from csv...")
        return importedNodes
    except:
        #파일이 존재하지 않는경우 빈값 반환
        return []

# nodelst.csv파일에 저장되어있는 모든 ip주소와 port번호로
# parameter는 생성된 blockchain객체들이 저장되어 있는 list이다.
def broadcastNewBlock(blockchain):
    #newBlock  = getLatestBlock(blockchain) # get the latest block
    #g_nodelstFileName이 존재하는 경우, 해당 파일의 한 행씩(IP주소와 port번호까지만)을 가져와 저장한 list 반환하여 importedNodes에 저장
    #존재하지 않는 경우, 빈 리스트 반환. 길이는 0
    importedNodes = readNodes(g_nodelstFileName) # get server node ip and port
    
    #nodelst.csv에 있는 모든 주소들로 요청을 보낼때 응답받는 쪽에서 받아야 할 내용의 header
    reqHeader = {'Content-Type': 'application/json; charset=utf-8'}
    #reqbody => dict자료형변수를 저장하는 list.
    reqBody = []
    # blockchain의 block객체들을 순차적으로 reqBody에 dict자료형으로 변환하여 저장한다.
    # 그 이유는 nodelst.csv의 모든 ip주소로 생성된 블록들의 정보를 json형식으로 보내야 하는데,
    # dict자료형으로 변환해야 json으로 dumps가 가능하기 때문이다.
    for i in blockchain:
        #참고사이트 : https://datascienceschool.net/view-notebook/800023e93aed4a19960490a2ba920f8b/
        reqBody.append(i.__dict__)

    #nodelst.csv가 존재하지 않는 경우는 건너 띈다. 존재하는 경우는 url에 ip주소 + port번호 + 모든블록의 내용을 조합하여 보낸다.
    if len(importedNodes) > 0 :
        for node in importedNodes:
            try:
                #ip주소와 port번호와 해당 ip주소의 blockchain 서버가 인식할수 있는 "/node/receiveNewBlock"를 붙인다.
                #block들의 내용은 post형식으로 따로 data에 저장되어 날아감.
                URL = "http://" + node[0] + ":" + node[1] + g_receiveNewBlock  # 형태 : http://ip:port/node/receiveNewBlock
                #전체 block들의 정보가 dict형태로 들어가있는 reqBody를 json.dumps로 인코딩하여 data에 저장하고,
                #headers 에는 reqHeader의 내용을 저장하여 requests.post에서 해당 URL로 전송한다.
                res = requests.post(URL, headers=reqHeader, data=json.dumps(reqBody))
                #전송이 제대로 되어서 응답이 왔다면,
                if res.status_code == 200:
                    print(URL + " sent ok.")
                    print("Response Message " + res.text)
                #전송이 제대로 되지 않았다는 응답이 왔다면,
                else:
                    print(URL + " responding error " + res.status_code)
            #requests.post가 모종의 이유로 전송이 되지 않았을 경우, 쓰기모드 파일스트림을 열고 읽기모드 파일스트림을 열어
            #nodelst.csv를 업데이트 한다.
            except:
                print(URL + " is not responding.")
                # write responding results
                # "nodelst.csv"를 쓰기모드로 파일스트림을 임시로 연다. 임시로 열기때문에 현재 scope에서만 쓰이고 없어짐.
                tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)
                try:
                    # "nodelst.csv"를 쓰기모드로 파일스트림을 임시로 연다. 임시로 열기때문에 현재 scope에서만 쓰이고 없어짐.
                    #해당 파일이 존재하지않다면, except로 빠진다.
                    with open(g_nodelstFileName, 'r', newline='') as csvfile, tempfile:
                        reader = csv.reader(csvfile)
                        writer = csv.writer(tempfile)
                        #nodelst.csv의 모든 행의 내용이 들어가있는 reader의 값들을 순차적으로 가져온다.
                        for row in reader:
                            #if row?
                            if row:
                                #?
                                if row[0] == node[0] and row[1] == node[1]:
                                    print("connection failed "+row[0]+":"+row[1]+", number of fail "+row[2])
                                    #row[2]는 전송시도횟수
                                    tmp = row[2]
                                    # too much fail, delete node
                                    #해당 ip주소와 port에 대해 g_maximumTry(100)번 이상의 전송시도를 실패했다면,
                                    if int(tmp) > g_maximumTry:
                                        print(row[0]+":"+row[1]+" deleted from node list because of exceeding the request limit")
                                    #아직 g_maximumTry(100)번 이상 만큼 전송시도를 하지 않았다면,
                                    else:
                                        #해당 ip주소의 전송시도 횟수를 하나 올리고 저장
                                        row[2] = int(tmp) + 1
                                        writer.writerow(row)
                                #?
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

def compareMerge(bcDict):

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

def initSvr():
    print("init Server")
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
    def do_GET(self):
        data = []  # response json data
        if None != re.search('/block/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            if None != re.search('/block/getBlockData', self.path):
                # TODO: range return (~/block/getBlockData?from=1&to=300)
                # queryString = urlparse(self.path).query.split('&')
                #blockchain.csv의 파일을 읽어온다. 모두는 external(외부). 처음에 아무런 블록체인이 없는 상태(blockchain.csv이 없는 상태)에서
                #readBlockchain은 internal의 경우 (    )을 리턴하고, external의 경우 None 을 리턴을 한다
                block = readBlockchain(g_bcFileName, mode = 'external')

                #block의 값이 None인 경우
                if block == None :
                    #블록이 존재하지 않음을 프린트하고,
                    print("No Block Exists")
                    #응답으로 보내줄 문자열을 data에 append시킨다.
                    data.append("no data exists")
                else :
                    for i in block:
                        print(i.__dict__)
                        data.append(i.__dict__)
                #"no data exists" 라는 메세지가 담긴 data를 json.dumps시키고 utf-8로 인코딩시켜서 bytes형으로 캐스팅하고 wfile.write에 씌워서 날린다.
                #블록체인데이터가 아무것도 없는 상태에서, 데이터를 확인 할 경우는 이곳에서 끝이난다.
                #그 다음은 블록체인을 최초로 생성할 때를 알아봐야한다. (generateBlcok, http://localhost:8099/block/generateBlock)
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))

            #블럭을 생성하는 경우 (최초, 그 이후 전부)
            elif None != re.search('/block/generateBlock', self.path):
                #mine 함수를 쓰레드로 돌린다. 이 부분을 쓰레드로 돌리는 이유는 채굴은 여러노드가 동시에 진행할 수 있기 때문이다.
                t = threading.Thread(target=mine)
                t.start()
                data.append("{mining is underway:check later by calling /block/getBlockData}")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))
            else:
                data.append("{info:no such api}")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))

        elif None != re.search('/node/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            if None != re.search('/node/addNode', self.path):
                queryStr = urlparse(self.path).query.split(':')
                print("client ip : "+self.client_address[0]+" query ip : "+queryStr[0])
                if self.client_address[0] != queryStr[0]:
                    data.append("your ip address doesn't match with the requested parameter")
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

    def do_POST(self):

        if None != re.search('/block/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            if None != re.search('/block/validateBlock/*', self.path):
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
            elif None != re.search('/block/newtx', self.path):
                ctype, pdict = cgi.parse_header(self.headers['content-type'])
                if ctype == 'application/json':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    receivedData = post_data.decode('utf-8')
                    print(type(receivedData))
                    tempDict = json.loads(receivedData)
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
            #새로운 블록이 생성되었을 때, 생성된 곳에서 다른 노드들에게 블록들에 대한 정보가 왔을 때 여기서 해결
            if None != re.search(g_receiveNewBlock, self.path): # /node/receiveNewBlock
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
    server = ThreadedHTTPServer(('', PORT_NUMBER), myHandler)
    print('Started httpserver on port ', PORT_NUMBER)

    initSvr()
    # Wait forever for incoming http requests
    server.serve_forever()

except (KeyboardInterrupt, Exception) as e:
    print('^C received, shutting down the web server')
    print(e)
    server.socket.close()