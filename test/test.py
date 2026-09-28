def string_splosions(string):
    temp=string[0]
    for i in range(0, len(string)):
        temp+=string[i]

    return temp

if __name__ == "__main__":
    print(string_splosions("Code"))
    print(string_splosions("abc"))
    print(string_splosions("ab"))
    print(string_splosions("a"))
    print(string_splosions(""))
