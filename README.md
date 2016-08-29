# Pox playground

## Run controller
`$ ./pox-wrapper.py log.level --DEBUG controller.loop_discovery`

`$ sudo mn --custom ring.py --topo ring --controller remote`

## Topology
```
            +-------+
            | / ___||
+-----------+| (___ +----------+
|           | \____||          |
|           +---+---+          |
|               |              |
|           *---+---*          |
|           |<-   ->|          |
|           +   X   +          |
|         / |<-   ->|\         |
|        /  *---+---* \        |
|       /       |      \       |
|      /        |       \      |
| *---+---*     |    *---+---* |
| |<-   ->|     |    |<-   ->| |
+-+   X   +----------+   X   +-+
  |<-   ->|     |    |<-   ->|  
  *---+---*     |    *---+---*  
      |         |        |      
   *--+--*   +--+-+   +--+--+   
   | H2  |   | H1 |   | H3  |   
   *-----*   +----+   +-----+   
```

## Inspect
`ovs-ofctl dump-flows s1`
