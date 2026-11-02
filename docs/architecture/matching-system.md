# MATCHING SYSTEM

The aim of integrating a matching system is to ensure students get mapped to the best tutors based on their prefrences. This system used the cosine similarity mertric to compare the similarity of a student vector to each tutor vector.  
Cosine similarity was selected because it provides a simple and effective way to measure how closely students and tutors align across multiple attributes. It returns a similarity score that makes it easy to rank tutors and recommend tutors that align most closely with the students requirements. It is also easy to scale as new preference criteria can be added to the vectors as the system evolves.  
Euclidean Distance was considered as an alternative but using Cosine Similarity proved to be more a more straighforward approach as it compares how the vectors align rather than focusing on the numerical difference between them.

![alt text](./diagrams/matching-system.png)

The system was adapted to capture learning prefrences using a sider scaled from 1- 5, 1 being the lowest prefrence and 5 representing the highest. With this approach, numerical values are easily extracted and ransformed to vectors in real time, while also providing a simple user experience.

When a student 
